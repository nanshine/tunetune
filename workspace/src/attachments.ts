import { labels } from './i18n';

// Attachments a trial input can carry; the service checks the same kinds, formats and sizes.
export type AttachmentKind = 'image' | 'audio' | 'video' | 'file';
// The formats each attachment kind accepts, as the service checks them; any extension for other files.
export const ATTACHMENT_FORMATS: Record<AttachmentKind, string[]> = { image: ['png', 'jpg', 'jpeg', 'gif', 'webp'], audio: ['wav', 'mp3', 'ogg', 'flac', 'm4a'], video: ['mp4', 'm4v', 'mov', 'webm'], file: [] };
export const ATTACHMENT_LIMIT_MB: Record<AttachmentKind, number> = { image: 16, audio: 64, video: 256, file: 256 };
export const pickLabels = labels({ image: '选择图片', audio: '选择音频', video: '选择视频', file: '选择文件' });
export const changeLabels = labels({ image: '换一张图片', audio: '换一段音频', video: '换一段视频', file: '换一个文件' });
export const dropLabels = labels({ image: '拖一张图片到这里', audio: '拖一段音频到这里', video: '拖一段视频到这里', file: '拖一个文件到这里' });
export const missingLabels = labels({ image: '先选一张图片', audio: '先选一段音频', video: '先选一段视频', file: '先选一个文件' });
export const formatLabels = labels({ image: '只能使用 PNG、JPEG、GIF 或 WebP 图片。', audio: '只能使用 WAV、MP3、OGG、FLAC 或 M4A 音频。', video: '只能使用 MP4、MOV 或 WebM 视频。', file: '文件需要一个只含字母或数字的扩展名。' });
export function attachmentExtension(file: File, kind: AttachmentKind): string | null {
  const ext = /\.([A-Za-z0-9]{1,8})$/.exec(file.name)?.[1].toLowerCase() ?? '';
  return ext && (kind === 'file' || ATTACHMENT_FORMATS[kind].includes(ext)) ? ext : null;
}
