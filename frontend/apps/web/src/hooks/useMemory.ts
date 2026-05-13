"use client";

import { useState, useCallback } from "react";

interface Memory {
  id: string;
  type: "working" | "episodic" | "semantic" | "procedural";
  content: string;
  importance: number;
  createdAt: Date;
  tags: string[];
}

interface UseMemoryReturn {
  memories: Memory[];
  isLoading: boolean;
  error: string | null;
  store: (content: any, type: string) => Promise<void>;
  retrieve: (query: string) => Promise<void>;
  clear: (conversationId?: string) => Promise<void>;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://api.rasospeak.ai";

export function useMemory(): UseMemoryReturn {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const getToken = () => localStorage.getItem("rasospeak_token");

  const store = useCallback(
    async (content: any, type: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const token = getToken();
        if (!token) throw new Error("Not authenticated");

        const response = await fetch(`${API_URL}/memory`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            Authorization: `Bearer ${token}`,
          },
          body: JSON.stringify({ content, memory_type: type }),
        });

        if (!response.ok) throw new Error("Failed to store memory");

        const data = await response.json();

        setMemories((prev) => [
          {
            id: data.memory_id,
            type: type as Memory["type"],
            content: JSON.stringify(content),
            importance: 0.5,
            createdAt: new Date(),
            tags: [],
          },
          ...prev,
        ]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const retrieve = useCallback(async (query: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const token = getToken();
      if (!token) throw new Error("Not authenticated");

      const response = await fetch(
        `${API_URL}/memory?query=${encodeURIComponent(query)}`,
        {
          headers: {
            Authorization: `Bearer ${token}`,
          },
        }
      );

      if (!response.ok) throw new Error("Failed to retrieve memories");

      const data = await response.json();

      // Parse the context into memory entries
      // In production, this would come as structured data
      const parsed: Memory[] = [];

      setMemories(parsed);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clear = useCallback(async (conversationId?: string) => {
    setIsLoading(true);
    setError(null);

    try {
      const token = getToken();
      if (!token) throw new Error("Not authenticated");

      // Clear working memory for conversation
      if (conversationId) {
        await fetch(`${API_URL}/memory/working/${conversationId}`, {
          method: "DELETE",
          headers: {
            Authorization: `Bearer ${token}`,
          },
        });
      }

      setMemories([]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setIsLoading(false);
    }
  }, []);

  return {
    memories,
    isLoading,
    error,
    store,
    retrieve,
    clear,
  };
}
