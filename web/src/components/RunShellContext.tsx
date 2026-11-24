"use client";

import { createContext, useContext, useState, type ReactNode } from "react";

type RunShellContextValue = {
  drawerOpen: boolean;
  setDrawerOpen: (open: boolean) => void;
};

const RunShellContext = createContext<RunShellContextValue>({
  drawerOpen: false,
  setDrawerOpen: () => {},
});

export function RunShellProvider({ children }: { children: ReactNode }) {
  const [drawerOpen, setDrawerOpen] = useState(false);
  return (
    <RunShellContext.Provider value={{ drawerOpen, setDrawerOpen }}>
      {children}
    </RunShellContext.Provider>
  );
}

export function useRunShell(): RunShellContextValue {
  return useContext(RunShellContext);
}
