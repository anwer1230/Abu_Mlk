import React from 'react';
import { X, Bot } from 'lucide-react';
import { useTelegram } from '../../context/TelegramContext';

export const SmartAiLearnModal: React.FC = () => {
  const { activeModal, setActiveModal, settings } = useTelegram();
  const isArabic = settings.language === 'ar';
  if (activeModal !== ('smart-ai-learn' as any)) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60">
      <div className="bg-[#17212b] text-white rounded-xl max-w-sm w-full p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-semibold">{isArabic ? 'الذكاء الاصطناعي الذكي' : 'Smart AI Learning'}</h3>
          <button onClick={() => setActiveModal('none')}><X className="w-5 h-5 text-gray-400" /></button>
        </div>
        <p className="text-xs text-gray-400 mb-4">{isArabic ? 'تدريب نماذج الذكاء الاصطناعي على الردود' : 'AI automated responses'}</p>
        <button onClick={() => setActiveModal('none')} className="w-full bg-[#2481cc] py-2 rounded-lg text-sm">{isArabic ? 'إغلاق' : 'Close'}</button>
      </div>
    </div>
  );
};
