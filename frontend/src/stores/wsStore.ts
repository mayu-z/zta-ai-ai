import { create } from "zustand";

import { createChatSocket, createPipelineMonitorSocket } from "@/lib/ws";
import type { PipelineMonitorFrame, TokenFrame } from "@/types";

interface WsState {
  socket: WebSocket | null;
  connected: boolean;
  monitorSocket: WebSocket | null;
  monitorConnected: boolean;
  connect: (token: string, onFrame: (frame: TokenFrame) => void, onError: (message: string) => void) => void;
  disconnect: () => void;
  send: (payload: { query: string }) => boolean;
  connectMonitor: (
    token: string,
    onFrame: (frame: PipelineMonitorFrame) => void,
    onError: (message: string) => void
  ) => void;
  disconnectMonitor: () => void;
}

export const useWsStore = create<WsState>((set, get) => ({
  socket: null,
  connected: false,
  monitorSocket: null,
  monitorConnected: false,
  connect: (token, onFrame, onError) => {
    const current = get().socket;
    if (current) {
      current.close();
    }

    const socket = createChatSocket(token, {
      onOpen: () => set({ connected: true }),
      onClose: () => set({ connected: false, socket: null }),
      onError,
      onFrame,
    });

    set({ socket, connected: false });
  },
  disconnect: () => {
    const socket = get().socket;
    if (socket) {
      socket.close();
    }
    set({ socket: null, connected: false });
  },
  send: (payload) => {
    const socket = get().socket;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return false;
    }

    socket.send(JSON.stringify(payload));
    return true;
  },
  connectMonitor: (token, onFrame, onError) => {
    const current = get().monitorSocket;
    if (current) {
      current.close();
    }

    const monitorSocket = createPipelineMonitorSocket(token, {
      onOpen: () => set({ monitorConnected: true }),
      onClose: () => set({ monitorConnected: false, monitorSocket: null }),
      onError,
      onFrame,
    });

    set({ monitorSocket, monitorConnected: false });
  },
  disconnectMonitor: () => {
    const monitorSocket = get().monitorSocket;
    if (monitorSocket) {
      monitorSocket.close();
    }
    set({ monitorSocket: null, monitorConnected: false });
  },
}));
