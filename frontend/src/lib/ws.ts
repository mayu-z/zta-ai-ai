import { API_BASE_URL } from "@/lib/api";
import type { PipelineMonitorFrame, TokenFrame } from "@/types";

const WS_BASE_URL = API_BASE_URL.replace(/^http/i, "ws");

function safeJsonParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export function createChatSocket(
  token: string,
  handlers: {
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (message: string) => void;
    onFrame?: (frame: TokenFrame) => void;
  }
): WebSocket {
  const socket = new WebSocket(`${WS_BASE_URL}/chat/stream?token=${encodeURIComponent(token)}`);

  socket.onopen = () => handlers.onOpen?.();
  socket.onclose = () => handlers.onClose?.();
  socket.onerror = () => handlers.onError?.("Chat socket disconnected");
  socket.onmessage = (event) => {
    const payload = safeJsonParse(event.data);
    if (!payload || typeof payload !== "object") {
      return;
    }
    handlers.onFrame?.(payload as TokenFrame);
  };

  return socket;
}

export function createPipelineMonitorSocket(
  token: string,
  handlers: {
    onOpen?: () => void;
    onClose?: () => void;
    onError?: (message: string) => void;
    onFrame?: (frame: PipelineMonitorFrame) => void;
  }
): WebSocket {
  const socket = new WebSocket(
    `${WS_BASE_URL}/admin/pipeline/monitor?token=${encodeURIComponent(token)}`
  );

  socket.onopen = () => handlers.onOpen?.();
  socket.onclose = () => handlers.onClose?.();
  socket.onerror = () => handlers.onError?.("Pipeline monitor disconnected");
  socket.onmessage = (event) => {
    const payload = safeJsonParse(event.data);
    if (!payload || typeof payload !== "object") {
      return;
    }
    handlers.onFrame?.(payload as PipelineMonitorFrame);
  };

  return socket;
}
