import { useEffect, useMemo, useRef, useState } from 'react';
import {
  Archive,
  Bell,
  BellOff,
  Check,
  CheckCheck,
  ChevronDown,
  Clipboard,
  FileText,
  Hash,
  Image,
  Info,
  Menu,
  MessageCircle,
  MoreHorizontal,
  Moon,
  Paperclip,
  PanelRight,
  Pin,
  Plus,
  Search,
  Send,
  Settings2,
  ShieldCheck,
  Smile,
  Sun,
  Trash2,
  UserRound,
  Volume2,
  VolumeX,
  X,
} from 'lucide-react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from '@/components/ui/toaster';
import { TooltipProvider } from '@/components/ui/tooltip';

type Folder = 'All' | 'Unread' | 'Work' | 'Personal';
type AvatarTone = 'saffron' | 'slate' | 'plum' | 'sage' | 'coral';
type Chat = {
  id: string;
  name: string;
  initials: string;
  tone: AvatarTone;
  handle: string;
  preview: string;
  time: string;
  unread: number;
  folder: Exclude<Folder, 'All' | 'Unread'>;
  online?: boolean;
  archived?: boolean;
  muted?: boolean;
  pinned?: boolean;
  bio: string;
  location: string;
};
type Message = {
  id: string;
  chatId: string;
  text: string;
  time: string;
  mine: boolean;
  status?: 'read' | 'sent';
  reaction?: string;
  attachment?: { name: string; size: string; kind: string };
};

const chatsSeed: Chat[] = [
  { id: 'layla', name: 'Layla Hassan', initials: 'LH', tone: 'saffron', handle: '@layla.h', preview: 'The light in this cafe is unreal.', time: '09:42', unread: 2, folder: 'Personal', online: true, pinned: true, bio: 'Product designer, occasional baker, always looking for the best quiet corner.', location: 'Cairo, Egypt' },
  { id: 'studio', name: 'Studio North', initials: 'SN', tone: 'slate', handle: '@studio_north', preview: 'Mika: I dropped the revised deck.', time: 'Yesterday', unread: 0, folder: 'Work', online: true, muted: true, bio: 'A small team making thoughtful digital products.', location: 'London · Cairo' },
  { id: 'omar', name: 'Omar El-Sayed', initials: 'OE', tone: 'plum', handle: '@omar.es', preview: 'على الرحب والسعة — see you Friday.', time: 'Tue', unread: 0, folder: 'Personal', online: false, bio: 'Photographer and collector of old maps.', location: 'Alexandria, Egypt' },
  { id: 'mina', name: 'Mina & You', initials: 'MY', tone: 'sage', handle: '@mina_adel', preview: 'You: Let’s keep the morning slow.', time: 'Mon', unread: 0, folder: 'Personal', online: true, bio: 'A private conversation.', location: 'Local workspace' },
  { id: 'research', name: 'Field Notes', initials: 'FN', tone: 'coral', handle: '@field_notes', preview: 'New voice memo · 0:42', time: 'Sun', unread: 7, folder: 'Work', online: false, bio: 'Shared research notes for the autumn project.', location: 'Workspace' },
  { id: 'sara', name: 'Sara Mansour', initials: 'SM', tone: 'slate', handle: '@sara.m', preview: 'Can you send the recipe?', time: 'Oct 14', unread: 0, folder: 'Personal', online: false, bio: 'Editor, reader, and amateur ceramicist.', location: 'Giza, Egypt' },
];

const messagesSeed: Message[] = [
  { id: 'm1', chatId: 'layla', text: 'Good morning. I found that tiny cafe we talked about.', time: '09:18', mine: false },
  { id: 'm2', chatId: 'layla', text: 'It is tucked behind the bookshop on Road 9. Very quiet, very good coffee.', time: '09:21', mine: false },
  { id: 'm3', chatId: 'layla', text: 'The light in this cafe is unreal.', time: '09:42', mine: false, reaction: 'heart' },
  { id: 'm4', chatId: 'layla', text: 'That sounds exactly like our kind of place. Saving it for Friday.', time: '09:45', mine: true, status: 'read' },
  { id: 'm5', chatId: 'layla', text: 'I will bring the little camera.', time: '09:46', mine: true, status: 'read' },
  { id: 'm6', chatId: 'studio', text: 'Quick check-in before the afternoon review. Are we happy with the new direction?', time: 'Yesterday', mine: false },
  { id: 'm7', chatId: 'studio', text: 'I dropped the revised deck. The opening is much calmer now.', time: 'Yesterday', mine: false, attachment: { name: 'north-review-v3.pdf', size: '2.4 MB', kind: 'document' } },
  { id: 'm8', chatId: 'studio', text: 'Yes, this is the right pace. I left two notes on slide 08.', time: 'Yesterday', mine: true, status: 'sent' },
  { id: 'm9', chatId: 'omar', text: 'مساء الخير، وصلت الصور؟', time: 'Tue', mine: false },
  { id: 'm10', chatId: 'omar', text: 'على الرحب والسعة — see you Friday.', time: 'Tue', mine: false },
  { id: 'm11', chatId: 'mina', text: 'You: Let’s keep the morning slow.', time: 'Mon', mine: true, status: 'read' },
  { id: 'm12', chatId: 'research', text: 'New voice memo · 0:42', time: 'Sun', mine: false, attachment: { name: 'site-walk.m4a', size: '1.1 MB', kind: 'audio' } },
  { id: 'm13', chatId: 'sara', text: 'Can you send the recipe?', time: 'Oct 14', mine: false },
];

const STORAGE = { chats: 'telegram-local-chats', messages: 'telegram-local-messages', prefs: 'telegram-local-prefs' };
const queryClient = new QueryClient();

function readStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? JSON.parse(raw) as T : fallback;
  } catch {
    return fallback;
  }
}

function Avatar({ chat, size = '' }: { chat: Pick<Chat, 'initials' | 'tone' | 'online'>; size?: string }) {
  return <div className={`avatar avatar-${chat.tone} ${size} ${chat.online ? '' : 'offline'}`} data-testid={`avatar-${chat.initials}`} aria-label={`${chat.initials} avatar`}>{chat.initials}</div>;
}

function IconButton({ label, children, onClick, active = false, testId }: { label: string; children: React.ReactNode; onClick: () => void; active?: boolean; testId: string }) {
  return <button type="button" className={`icon-button ${active ? 'is-on' : ''}`} title={label} aria-label={label} onClick={onClick} data-testid={testId}>{children}</button>;
}

function Home() {
  const [chats, setChats] = useState<Chat[]>(() => readStored(STORAGE.chats, chatsSeed));
  const [messages, setMessages] = useState<Message[]>(() => readStored(STORAGE.messages, messagesSeed));
  const [prefs, setPrefs] = useState(() => readStored(STORAGE.prefs, { dark: false, notifications: true }));
  const [selectedId, setSelectedId] = useState('layla');
  const [folder, setFolder] = useState<Folder>('All');
  const [query, setQuery] = useState('');
  const [messageQuery, setMessageQuery] = useState('');
  const [draft, setDraft] = useState('');
  const [mobileChatsOpen, setMobileChatsOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(true);
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatName, setNewChatName] = useState('');
  const [newChatHandle, setNewChatHandle] = useState('');
  const [newTone, setNewTone] = useState<AvatarTone>('coral');
  const [toast, setToast] = useState('');
  const [attachment, setAttachment] = useState<{ name: string; size: string; kind: string } | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);
  const composeRef = useRef<HTMLTextAreaElement>(null);

  const selected = chats.find((chat) => chat.id === selectedId) ?? chats[0];
  const selectedMessages = useMemo(() => messages.filter((message) => message.chatId === selectedId), [messages, selectedId]);
  const visibleChats = useMemo(() => chats.filter((chat) => {
    const matchesFolder = folder === 'All' || (folder === 'Unread' ? chat.unread > 0 : chat.folder === folder);
    const haystack = `${chat.name} ${chat.preview} ${chat.handle}`.toLowerCase();
    return !chat.archived && matchesFolder && haystack.includes(query.toLowerCase());
  }), [chats, folder, query]);
  const archived = chats.filter((chat) => chat.archived);
  const searchHits = messageQuery.trim() ? selectedMessages.filter((message) => message.text.toLowerCase().includes(messageQuery.toLowerCase())) : selectedMessages;

  useEffect(() => { localStorage.setItem(STORAGE.chats, JSON.stringify(chats)); }, [chats]);
  useEffect(() => { localStorage.setItem(STORAGE.messages, JSON.stringify(messages)); }, [messages]);
  useEffect(() => {
    localStorage.setItem(STORAGE.prefs, JSON.stringify(prefs));
    document.documentElement.classList.toggle('dark', prefs.dark);
  }, [prefs]);
  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(''), 2400);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const showToast = (message: string) => setToast(message);
  const updateSelected = (update: Partial<Chat>) => setChats((current) => current.map((chat) => chat.id === selectedId ? { ...chat, ...update } : chat));
  const selectChat = (id: string) => {
    setSelectedId(id);
    setMessageQuery('');
    setMobileChatsOpen(false);
    setChats((current) => current.map((chat) => chat.id === id ? { ...chat, unread: 0 } : chat));
  };
  const sendMessage = () => {
    const text = draft.trim();
    if (!text && !attachment) return;
    const now = new Date();
    const time = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    const newMessage: Message = { id: `m-${Date.now()}`, chatId: selectedId, text, time, mine: true, status: 'sent', attachment: attachment ?? undefined };
    setMessages((current) => [...current, newMessage]);
    updateSelected({ preview: attachment ? attachment.name : text, time, unread: 0 });
    setDraft('');
    setAttachment(null);
    if (composeRef.current) composeRef.current.style.height = 'auto';
  };
  const handleComposeKey = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); sendMessage(); }
  };
  const onFile = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const kind = file.type.startsWith('image/') ? 'image' : file.type.startsWith('audio/') ? 'audio' : 'document';
    setAttachment({ name: file.name, size: `${Math.max(file.size / 1024, .1).toFixed(1)} KB`, kind });
    showToast('Attachment staged locally');
    event.target.value = '';
  };
  const createChat = (event: React.FormEvent) => {
    event.preventDefault();
    const name = newChatName.trim();
    if (!name) return;
    const id = `local-${Date.now()}`;
    const initials = name.split(/\s+/).slice(0, 2).map((part) => part[0]).join('').toUpperCase();
    const chat: Chat = { id, name, initials, tone: newTone, handle: newChatHandle.trim() || '@local_contact', preview: 'New local conversation', time: 'now', unread: 0, folder: 'Personal', online: false, bio: 'A conversation saved on this device.', location: 'Local workspace' };
    setChats((current) => [chat, ...current]);
    setMessages((current) => [...current, { id: `${id}-welcome`, chatId: id, text: 'This conversation is ready for local messages.', time: 'now', mine: false }]);
    setSelectedId(id);
    setNewChatName('');
    setNewChatHandle('');
    setNewChatOpen(false);
    setMobileChatsOpen(false);
    showToast('Local chat created');
  };
  const clearLocalData = () => {
    localStorage.removeItem(STORAGE.chats);
    localStorage.removeItem(STORAGE.messages);
    setChats(chatsSeed);
    setMessages(messagesSeed);
    setSelectedId('layla');
    setFolder('All');
    setQuery('');
    showToast('Local workspace restored to sample data');
  };

  if (!selected) return <div className="empty-state"><div><div className="empty-symbol"><MessageCircle size={25} /></div><div className="empty-title">Your desk is quiet</div></div></div>;

  return (
    <main className="app-shell" data-testid="app-shell">
      <div className="app-frame">
        <aside className={`pane left-pane ${mobileChatsOpen ? 'is-mobile-open' : ''}`} aria-label="Chats">
          <div className="pane-header">
            <div className="topline">
              <div className="brand-lockup">
                <div className="brand-mark"><MessageCircle size={18} strokeWidth={2.2} /></div>
                <div><div className="brand-title">local desk</div><div className="eyebrow">private workspace</div></div>
              </div>
              <IconButton label="Open settings" onClick={() => setInfoOpen(true)} testId="button-open-settings"><Settings2 size={17} /></IconButton>
            </div>
            <div className="brand-subtitle">A familiar place for messages, kept on your device.</div>
            <div className="search-wrap">
              <Search className="search-icon" size={16} />
              <input className="search-input" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search chats" aria-label="Search chats" data-testid="input-search-chats" />
              <span className="search-key">⌘ K</span>
            </div>
          </div>
          <div className="folder-tabs" role="tablist" aria-label="Chat folders">
            {(['All', 'Unread', 'Work', 'Personal'] as Folder[]).map((item) => <button type="button" role="tab" aria-selected={folder === item} className={`folder-tab ${folder === item ? 'is-active' : ''}`} onClick={() => setFolder(item)} key={item} data-testid={`tab-folder-${item.toLowerCase()}`}>{item}{item === 'Unread' && <span className="ml-1 opacity-70">{chats.reduce((sum, chat) => sum + chat.unread, 0)}</span>}</button>)}
          </div>
          <div className="chat-list">
            <div className="chat-section-label"><span>Conversations</span><button type="button" className="icon-button !h-6 !w-6" title="Start a new chat" aria-label="Start a new chat" onClick={() => setNewChatOpen(true)} data-testid="button-new-chat"><Plus size={15} /></button></div>
            {visibleChats.map((chat) => <button type="button" className={`chat-row ${chat.id === selectedId ? 'is-selected' : ''}`} onClick={() => selectChat(chat.id)} key={chat.id} data-testid={`chat-row-${chat.id}`}>
              <Avatar chat={chat} />
              <span className="chat-copy"><span className="chat-name-line"><span className="chat-name">{chat.name}</span><span className="chat-time">{chat.time}</span></span><span className="chat-preview-line">{chat.pinned && <Pin size={11} className="text-[hsl(var(--primary))]" />}<span className="chat-preview">{chat.preview}</span>{chat.unread > 0 && <span className="unread-count">{chat.unread}</span>}</span></span>
            </button>)}
            {visibleChats.length === 0 && <div className="px-3 py-10 text-center text-xs text-[hsl(var(--muted-foreground))]" data-testid="empty-chat-results">No local chats match that search.</div>}
            {archived.length > 0 && <><div className="chat-section-label"><span>Stored away</span></div><button type="button" className="archive-row" onClick={() => { setFolder('All'); setQuery(''); showToast(`${archived.length} archived chat${archived.length > 1 ? 's' : ''} hidden from the list`); }} data-testid="button-show-archive"><Archive size={15} /><span>Archived chats</span><span className="ml-auto font-mono text-[10px]">{archived.length}</span></button></>}
          </div>
          <div className="left-footer">
            <button type="button" className="profile-button" onClick={() => setInfoOpen(true)} title="Open your profile and settings" data-testid="button-profile-settings"><div className="avatar avatar-sage small">AK</div><span><span className="profile-name">Amina Khalil</span><span className="profile-status"><span className="status-dot" />local only</span></span></button>
            <IconButton label={prefs.dark ? 'Use light theme' : 'Use dark theme'} onClick={() => setPrefs((current: typeof prefs) => ({ ...current, dark: !current.dark }))} testId="button-toggle-theme">{prefs.dark ? <Sun size={16} /> : <Moon size={16} />}</IconButton>
          </div>
        </aside>

        <section className="pane middle-pane" aria-label="Conversation">
          <header className="conversation-head">
            <div className="conversation-contact">
              <IconButton label="Show chat list" onClick={() => setMobileChatsOpen(true)} testId="button-mobile-chats"><Menu size={18} /></IconButton>
              <div className="mobile-back"><IconButton label="Show chat list" onClick={() => setMobileChatsOpen(true)} testId="button-mobile-back"><ChevronDown size={18} className="rotate-90" /></IconButton></div>
              <Avatar chat={selected} />
              <div className="contact-copy"><div className="contact-name" data-testid="text-selected-chat">{selected.name}</div><div className="contact-state"><span className="status-dot" />{selected.online ? 'active now' : 'local contact'}</div></div>
            </div>
            <div className="head-actions">
              <IconButton label={selected.pinned ? 'Unpin conversation' : 'Pin conversation'} active={selected.pinned} onClick={() => updateSelected({ pinned: !selected.pinned })} testId="button-toggle-pin"><Pin size={16} /></IconButton>
              <IconButton label={selected.muted ? 'Unmute conversation' : 'Mute conversation'} active={selected.muted} onClick={() => updateSelected({ muted: !selected.muted })} testId="button-toggle-mute">{selected.muted ? <VolumeX size={16} /> : <Volume2 size={16} />}</IconButton>
              <IconButton label="Toggle conversation details" active={infoOpen} onClick={() => setInfoOpen((value) => !value)} testId="button-toggle-info"><PanelRight size={16} /></IconButton>
              <div className="relative"><IconButton label="More conversation actions" onClick={() => setMenuOpen((value) => !value)} testId="button-conversation-menu"><MoreHorizontal size={17} /></IconButton>{menuOpen && <div className="absolute right-0 top-10 z-20 w-40 overflow-hidden rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-1 shadow-[var(--shadow-float)]"><button type="button" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-xs hover:bg-[hsl(var(--muted))]" onClick={() => { updateSelected({ archived: true }); setMenuOpen(false); setMobileChatsOpen(true); showToast('Conversation archived locally'); }} data-testid="button-archive-chat"><Archive size={14} />Archive chat</button></div>}</div>
            </div>
          </header>
          <div className="messages-area" data-testid="message-list">
            <div className="date-stamp"><span>Today · local timeline</span></div>
            {messageQuery && <div className="search-result-banner" data-testid="status-message-search"><span>Searching this conversation for “{messageQuery}”</span><button type="button" className="icon-button !h-6 !w-6" onClick={() => setMessageQuery('')} title="Clear message search" aria-label="Clear message search" data-testid="button-clear-message-search"><X size={13} /></button></div>}
            {searchHits.length === 0 && <div className="empty-state min-h-[250px]" data-testid="empty-message-search"><div><div className="empty-symbol"><Search size={23} /></div><div className="empty-title text-base">No messages found</div><div className="empty-copy">Try another word in this local conversation.</div></div></div>}
            {searchHits.map((message) => <MessageBubble key={message.id} message={message} onReact={() => setMessages((current) => current.map((item) => item.id === message.id ? { ...item, reaction: item.reaction ? undefined : 'heart' } : item))} />)}
          </div>
          <div className="compose-shell">
            {attachment && <div className="attachment-card" data-testid="status-attachment-preview"><div className="attachment-icon">{attachment.kind === 'image' ? <Image size={15} /> : <FileText size={15} />}</div><div className="attachment-copy"><div className="attachment-name">{attachment.name}</div><div className="attachment-size">{attachment.size} · ready to send locally</div></div><button type="button" className="icon-button !ml-auto !h-7 !w-7" title="Remove attachment" aria-label="Remove attachment" onClick={() => setAttachment(null)} data-testid="button-remove-attachment"><X size={14} /></button></div>}
            <div className="compose-box">
              <button type="button" className="compose-tool" title="Attach a local file" aria-label="Attach a local file" onClick={() => fileRef.current?.click()} data-testid="button-attach-file"><Paperclip size={17} /></button>
              <input ref={fileRef} type="file" className="hidden" onChange={onFile} aria-label="Choose a local attachment" data-testid="input-attachment" />
              <textarea ref={composeRef} className="compose-textarea" value={draft} onChange={(event) => { setDraft(event.target.value); event.currentTarget.style.height = 'auto'; event.currentTarget.style.height = `${Math.min(event.currentTarget.scrollHeight, 100)}px`; }} onKeyDown={handleComposeKey} placeholder={`Message ${selected.name}`} rows={1} aria-label={`Message ${selected.name}`} data-testid="input-message-compose" />
              <button type="button" className="compose-tool" title="Add a reaction symbol" aria-label="Add a reaction symbol" onClick={() => setDraft((value) => `${value}${value ? ' ' : ''}thanks`)} data-testid="button-compose-emoji"><Smile size={17} /></button>
              <button type="button" className="send-button" title="Send message" aria-label="Send message" onClick={sendMessage} data-testid="button-send-message"><Send size={16} /></button>
            </div>
            <div className="compose-note"><span><strong>Enter</strong> to send · shift + enter for a new line</span><span>stored on this device</span></div>
          </div>
        </section>

        {infoOpen && <aside className="pane right-pane" aria-label="Conversation details and settings">
          <div className="info-header"><div className="info-header-row"><div><div className="eyebrow">workspace / details</div><div className="info-title">Your local desk</div></div><IconButton label="Close details" onClick={() => setInfoOpen(false)} testId="button-close-info"><X size={16} /></IconButton></div></div>
          <div className="info-content">
            <div className="profile-card" data-testid="card-contact-details"><div className="profile-hero"><Avatar chat={selected} size="large" /><div><div className="profile-card-name">{selected.name}</div><div className="profile-card-handle">{selected.handle}</div></div></div><div className="profile-bio">{selected.bio}</div></div>
            <div className="info-section"><div className="section-caption">Contact details</div><div className="detail-row"><div className="detail-icon"><Hash size={14} /></div><div><div className="detail-label">Handle</div><div className="detail-value">{selected.handle}</div></div></div><div className="detail-row"><div className="detail-icon"><Info size={14} /></div><div><div className="detail-label">Location</div><div className="detail-value">{selected.location}</div></div></div></div>
            <div className="info-section"><div className="section-caption">Conversation</div><div className="action-list"><button type="button" className={`action-button ${selected.pinned ? 'is-on' : ''}`} onClick={() => updateSelected({ pinned: !selected.pinned })} data-testid="button-details-pin"><span className="action-leading"><Pin size={15} /><span>{selected.pinned ? 'Pinned to top' : 'Pin to top'}</span></span>{selected.pinned && <Check size={14} className="tiny-check" />}</button><button type="button" className={`action-button ${selected.muted ? 'is-on' : ''}`} onClick={() => updateSelected({ muted: !selected.muted })} data-testid="button-details-mute"><span className="action-leading">{selected.muted ? <BellOff size={15} /> : <Bell size={15} />}<span>{selected.muted ? 'Notifications muted' : 'Notifications on'}</span></span><span className={`switch-control ${selected.muted ? '' : 'is-on'}`} /></button><button type="button" className="action-button" onClick={() => { updateSelected({ archived: true }); setMobileChatsOpen(true); showToast('Conversation archived locally'); }} data-testid="button-details-archive"><span className="action-leading"><Archive size={15} /><span>Archive conversation</span></span></button></div></div>
            <div className="info-section"><div className="section-caption">App preferences</div><div className="action-list"><button type="button" className="action-button" onClick={() => setPrefs((current: typeof prefs) => ({ ...current, dark: !current.dark }))} data-testid="button-settings-theme"><span className="action-leading">{prefs.dark ? <Sun size={15} /> : <Moon size={15} />}<span>{prefs.dark ? 'Light theme' : 'Dark theme'}</span></span><span className={`switch-control ${prefs.dark ? 'is-on' : ''}`} /></button><button type="button" className="action-button" onClick={() => setPrefs((current: typeof prefs) => ({ ...current, notifications: !current.notifications }))} data-testid="button-settings-notifications"><span className="action-leading">{prefs.notifications ? <Bell size={15} /> : <BellOff size={15} />}<span>Desktop notifications</span></span><span className={`switch-control ${prefs.notifications ? 'is-on' : ''}`} /></button><button type="button" className="action-button" onClick={clearLocalData} data-testid="button-clear-local-data"><span className="action-leading"><Trash2 size={15} /><span>Reset sample workspace</span></span></button></div></div>
            <div className="local-card" data-testid="status-local-mode"><ShieldCheck size={17} /><div><div className="local-card-title">Offline / local mode</div><div className="local-card-copy">Nothing leaves this browser. An official Telegram connection is not authorized here.</div></div></div>
          </div>
        </aside>}
      </div>
      {newChatOpen && <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setNewChatOpen(false); }}><form className="modal-card" onSubmit={createChat} aria-label="Create new local chat" data-testid="modal-new-chat"><div className="modal-head"><div><div className="eyebrow">new local thread</div><div className="modal-title">Start a conversation</div><div className="modal-copy">Create a contact in this browser. No account or network connection is required.</div></div><button type="button" className="modal-close" title="Close new chat" aria-label="Close new chat" onClick={() => setNewChatOpen(false)} data-testid="button-close-new-chat"><X size={17} /></button></div><div className="form-field"><label className="form-label" htmlFor="new-chat-name">Name</label><input id="new-chat-name" autoFocus className="form-input" value={newChatName} onChange={(event) => setNewChatName(event.target.value)} placeholder="e.g. Noor Ibrahim" data-testid="input-new-chat-name" /></div><div className="form-field"><label className="form-label" htmlFor="new-chat-handle">Handle <span className="font-normal text-[hsl(var(--muted-foreground))]">(optional)</span></label><input id="new-chat-handle" className="form-input" value={newChatHandle} onChange={(event) => setNewChatHandle(event.target.value)} placeholder="@local_contact" data-testid="input-new-chat-handle" /></div><div className="form-field"><div className="form-label">Avatar color</div><div className="avatar-choice">{(['coral', 'saffron', 'slate', 'plum', 'sage'] as AvatarTone[]).map((tone) => <button type="button" className={newTone === tone ? 'is-selected' : ''} onClick={() => setNewTone(tone)} key={tone} aria-label={`Choose ${tone} avatar`} data-testid={`button-avatar-tone-${tone}`}><div className={`avatar avatar-${tone} small`}>N</div></button>)}</div></div><div className="modal-submit"><button type="button" className="secondary-button" onClick={() => setNewChatOpen(false)} data-testid="button-cancel-new-chat">Cancel</button><button type="submit" className="primary-button" data-testid="button-create-new-chat">Create local chat</button></div></form></div>}
      {toast && <div className="toast-note" role="status" data-testid="status-toast">{toast}</div>}
    </main>
  );
}

function MessageBubble({ message, onReact }: { message: Message; onReact: () => void }) {
  return <div className={`message-line ${message.mine ? 'mine' : ''}`} data-testid={`message-row-${message.id}`}><div className="message-bubble" tabIndex={0} aria-label={`${message.mine ? 'You' : 'Contact'} said ${message.text}`} data-testid={`message-bubble-${message.id}`}>{message.attachment && <div className="attachment-card"><div className="attachment-icon">{message.attachment.kind === 'audio' ? <Volume2 size={15} /> : <FileText size={15} />}</div><div className="attachment-copy"><div className="attachment-name">{message.attachment.name}</div><div className="attachment-size">{message.attachment.size} · local attachment</div></div></div>}<div className="message-text">{message.text}</div><div className="message-meta"><span>{message.time}</span>{message.mine && (message.status === 'read' ? <CheckCheck size={13} /> : <Check size={13} />)}</div>{message.reaction && <div className="reaction-row"><button type="button" className="reaction-button is-active" onClick={onReact} title="Remove reaction" aria-label="Remove reaction" data-testid={`button-remove-reaction-${message.id}`}>♥ <span>1</span></button></div>}</div>{!message.reaction && <button type="button" className="reaction-button self-end !mb-1 !opacity-0 hover:!opacity-100 focus:!opacity-100" onClick={onReact} title="React to message" aria-label="React to message" data-testid={`button-react-message-${message.id}`}>♥</button>}</div>;
}

function App() {
  return <QueryClientProvider client={queryClient}><TooltipProvider><Home /><Toaster /></TooltipProvider></QueryClientProvider>;
}

export default App;