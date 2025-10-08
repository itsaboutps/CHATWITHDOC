import React from 'react';

export interface MessageBubbleProps { role: 'user'|'assistant'; content: string; sources?: string[]; answer_type?: string; document_ids_used?: number[]; embed_mode?: string; generation_mode?: string }

export const MessageBubble: React.FC<MessageBubbleProps> = ({ role, content, sources, answer_type, document_ids_used, embed_mode, generation_mode }) => {
  const isUser = role === 'user';
  return (
    <div className={isUser ? 'text-right' : 'text-left'}>
      <div className={`relative inline-block max-w-full px-4 py-3 rounded-2xl text-sm shadow-sm whitespace-pre-wrap break-words ${isUser ? 'bg-gradient-to-br from-indigo-600 to-blue-600 text-white' : 'bg-gray-100 dark:bg-gray-800 dark:text-gray-100 text-gray-800'}`}>
        {content}
        {role === 'assistant' && (
          <div className="mt-2 flex flex-wrap gap-2 items-center text-xs opacity-80">
            {answer_type && <span className="px-2 py-0.5 rounded bg-indigo-50 text-indigo-600 dark:bg-indigo-600/30 dark:text-indigo-200 capitalize">{answer_type}</span>}
            {embed_mode && <span className="px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300" title="Embedding mode">emb:{embed_mode}</span>}
            {generation_mode && <span className="px-2 py-0.5 rounded bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-300" title="Generation mode">gen:{generation_mode}</span>}
            {sources && sources.length>0 && <span className="truncate">Sources: {sources.slice(0,4).join(', ')}{sources.length>4?'…':''}</span>}
            {document_ids_used && document_ids_used.length>0 && <span className="text-gray-500">Docs used: {document_ids_used.length}</span>}
          </div>
        )}
      </div>
    </div>
  );
}
