import { create } from "zustand";
import type { ManagedFile, ServerFile } from "@/types";

type FileStore = {
  queue: ManagedFile[];
  serverFiles: ServerFile[];
  selectedId?: string;
  concurrency: number;
  addFiles: (files: ManagedFile[]) => void;
  updateFile: (id: string, patch: Partial<ManagedFile>) => void;
  setServerFiles: (files: ServerFile[]) => void;
  addServerFile: (file: ServerFile) => void;
  removeServerFile: (id: string) => void;
  setConcurrency: (value: number) => void;
  select: (id?: string) => void;
};

export const useFileStore = create<FileStore>((set) => ({
  queue: [],
  serverFiles: [],
  selectedId: undefined,
  concurrency: 2,
  addFiles: (files) =>
    set((state) => ({
      queue: [...files, ...state.queue],
      selectedId: files[0]?.id ?? state.selectedId,
    })),
  updateFile: (id, patch) =>
    set((state) => ({ queue: state.queue.map((item) => (item.id === id ? { ...item, ...patch } : item)) })),
  setServerFiles: (files) => set({ serverFiles: files }),
  addServerFile: (file) => set((state) => ({ serverFiles: [file, ...state.serverFiles] })),
  removeServerFile: (id) => set((state) => ({ serverFiles: state.serverFiles.filter((item) => item.id !== id) })),
  setConcurrency: (value) => set({ concurrency: Math.min(8, Math.max(1, Math.round(value))) }),
  select: (id) => set({ selectedId: id }),
}));
