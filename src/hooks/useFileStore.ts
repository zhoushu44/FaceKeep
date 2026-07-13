import { create } from "zustand";
import type { ManagedFile, ServerFile } from "@/types";

type FileStore = {
  queue: ManagedFile[];
  serverFiles: ServerFile[];
  selectedId?: string;
  addFiles: (files: ManagedFile[]) => void;
  updateFile: (id: string, patch: Partial<ManagedFile>) => void;
  setServerFiles: (files: ServerFile[]) => void;
  addServerFile: (file: ServerFile) => void;
  removeServerFile: (id: string) => void;
  select: (id?: string) => void;
};

export const useFileStore = create<FileStore>((set) => ({
  queue: [],
  serverFiles: [],
  selectedId: undefined,
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
  select: (id) => set({ selectedId: id }),
}));
