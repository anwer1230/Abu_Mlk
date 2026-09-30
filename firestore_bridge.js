import { initializeApp } from 'firebase/app';
import { 
  getFirestore, 
  collection, 
  getDocs, 
  doc, 
  setDoc, 
  deleteDoc, 
  getDoc,
  query,
  orderBy 
} from 'firebase/firestore';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const configPath = path.join(__dirname, 'firebase-applet-config.json');
const firebaseConfig = JSON.parse(fs.readFileSync(configPath, 'utf8'));

const app = initializeApp(firebaseConfig);
const db = getFirestore(app, firebaseConfig.firestoreDatabaseId);

const DEFAULT_PHONE_NUMBERS = [
  '+573244867204',
  '+201221349790',
  '+201148863243',
  '+213797500921',
  '+201274386864',
  '+201120945094',
  '+966539709737'
];

async function ensureDefaultPhones() {
  for (const phone of DEFAULT_PHONE_NUMBERS) {
    const docId = phone.replace(/[^0-9]/g, '');
    const docRef = doc(db, 'saved_phone_numbers', docId);
    const snap = await getDoc(docRef);
    if (!snap.exists()) {
      await setDoc(docRef, {
        phone_number: phone,
        added_at: new Date().toISOString(),
        is_default: true,
        label: 'رقم أساسي'
      });
    }
  }
}

async function getPhoneNumbers() {
  await ensureDefaultPhones();
  const snap = await getDocs(collection(db, 'saved_phone_numbers'));
  const list = [];
  snap.forEach(d => {
    list.push(d.data());
  });
  // Sort defaults first, then by added_at desc
  list.sort((a, b) => {
    if (a.is_default && !b.is_default) return -1;
    if (!a.is_default && b.is_default) return 1;
    return (b.added_at || '').localeCompare(a.added_at || '');
  });
  return list;
}

async function addPhoneNumber(phone, label = 'رقم محفوظ') {
  if (!phone || typeof phone !== 'string') return null;
  const cleanPhone = phone.trim();
  const docId = cleanPhone.replace(/[^0-9]/g, '');
  if (!docId) return null;
  const docRef = doc(db, 'saved_phone_numbers', docId);
  const snap = await getDoc(docRef);
  if (!snap.exists()) {
    const isDefault = DEFAULT_PHONE_NUMBERS.includes(cleanPhone);
    const data = {
      phone_number: cleanPhone,
      added_at: new Date().toISOString(),
      is_default: isDefault,
      label: isDefault ? 'رقم أساسي' : label
    };
    await setDoc(docRef, data);
    return data;
  }
  return snap.data();
}

async function getSavedLinks() {
  const snap = await getDocs(collection(db, 'saved_links'));
  const links = [];
  snap.forEach(d => {
    links.push({ id: d.id, ...d.data() });
  });
  links.sort((a, b) => (b.date_saved || '').localeCompare(a.date_saved || ''));
  return links;
}

async function addSavedLink(linkData) {
  if (!linkData || !linkData.url) return null;
  const id = linkData.id || ('link_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6));
  const docRef = doc(db, 'saved_links', id);
  const data = {
    id,
    url: linkData.url,
    title: linkData.title || linkData.url,
    category: linkData.category || 'عام',
    date_saved: linkData.date_saved || new Date().toISOString(),
    source: linkData.source || 'يدوي',
    notes: linkData.notes || ''
  };
  await setDoc(docRef, data, { merge: true });
  return data;
}

async function deleteSavedLink(id) {
  if (!id) return false;
  await deleteDoc(doc(db, 'saved_links', id));
  return true;
}

function normalizeReportId(raw) {
  if (!raw) return '';
  return String(raw).trim().toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/^(?:t\.me|telegram\.me)\//, '')
    .replace(/^@/, '')
    .replace(/[^a-zA-Z0-9_\-]/g, '_')
    .slice(0, 120);
}

async function getGroupSafetyReport(key) {
  const docId = normalizeReportId(key);
  if (!docId) return null;
  
  // 1. Try reading from saved_links (guaranteed permission)
  try {
    const linkDocRef = doc(db, 'saved_links', 'report_' + docId);
    const snap = await getDoc(linkDocRef);
    if (snap.exists()) {
      const d = snap.data();
      return d.report_data || d;
    }
  } catch (e) {
    // continue
  }

  // 2. Try group_safety_reports collection
  try {
    const docRef = doc(db, 'group_safety_reports', docId);
    const snap2 = await getDoc(docRef);
    if (snap2.exists()) {
      return snap2.data();
    }
  } catch (e) {
    // continue
  }

  return null;
}

async function saveGroupSafetyReport(reportData) {
  if (!reportData) return null;
  const key = reportData.group_key || reportData.group_id || reportData.username || reportData.group_title;
  const docId = normalizeReportId(key);
  if (!docId) return null;

  const nowIso = new Date().toISOString();
  const cleanData = {
    ...reportData,
    doc_id: docId,
    group_key: String(key),
    updated_at: nowIso
  };

  // 1. Save in saved_links (guaranteed allowed by Firestore rules)
  try {
    const linkDocRef = doc(db, 'saved_links', 'report_' + docId);
    await setDoc(linkDocRef, {
      id: 'report_' + docId,
      url: String(key),
      title: reportData.group_title || String(key),
      category: 'safety_report',
      type: 'safety_report',
      date_saved: nowIso,
      source: 'group_ai_analyzer',
      report_data: cleanData
    }, { merge: true });
  } catch (err) {
    console.error('Error saving to saved_links/report_' + docId + ':', err.message);
  }

  return cleanData;
}

async function getAllGroupSafetyReports() {
  const reports = [];
  try {
    const snap = await getDocs(collection(db, 'saved_links'));
    snap.forEach(d => {
      const data = d.data();
      if (d.id.startsWith('report_') || data.category === 'safety_report' || data.type === 'safety_report') {
        reports.push(data.report_data || data);
      }
    });
  } catch (e) {
    console.error('Error getting all group safety reports:', e.message);
  }
  return reports;
}

// CLI handler
const action = process.argv[2];
try {
  if (action === 'get_phones') {
    const phones = await getPhoneNumbers();
    console.log(JSON.stringify({ success: true, phones }));
  } else if (action === 'add_phone') {
    const phone = process.argv[3];
    const res = await addPhoneNumber(phone);
    console.log(JSON.stringify({ success: true, phone: res }));
  } else if (action === 'get_links') {
    const links = await getSavedLinks();
    console.log(JSON.stringify({ success: true, links }));
  } else if (action === 'add_link') {
    const data = JSON.parse(process.argv[3] || '{}');
    const res = await addSavedLink(data);
    console.log(JSON.stringify({ success: true, link: res }));
  } else if (action === 'delete_link') {
    const id = process.argv[3];
    await deleteSavedLink(id);
    console.log(JSON.stringify({ success: true, id }));
  } else if (action === 'get_group_report') {
    const key = process.argv[3];
    const report = await getGroupSafetyReport(key);
    console.log(JSON.stringify({ success: true, report }));
  } else if (action === 'save_group_report') {
    const data = JSON.parse(process.argv[3] || '{}');
    const saved = await saveGroupSafetyReport(data);
    console.log(JSON.stringify({ success: true, report: saved }));
  } else if (action === 'get_all_group_reports') {
    const reports = await getAllGroupSafetyReports();
    console.log(JSON.stringify({ success: true, reports }));
  } else {
    console.log(JSON.stringify({ error: 'Unknown action' }));
  }
} catch (err) {
  console.error(JSON.stringify({ success: false, error: err.message }));
  process.exit(1);
}
process.exit(0);
