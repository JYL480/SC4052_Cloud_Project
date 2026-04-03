const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000/api";

export type CreateThreadResponse = {
  thread_id: string;
  user_id: string;
  message: string;
};

export type ChatRequest = {
  thread_id: string;
  user_id: string;
  message: string;
};

export type ResumeRequest = {
  thread_id: string;
  user_id: string;
  decision: "approve" | "reject";
};

export type ResumeResponse = {
  thread_id: string;
  user_id: string;
  reply: string;
};

export type ChatSseEvent =
  | { type: "node"; node: string }
  | { type: "message"; node: string; content: string }
  | { type: "interrupt"; details?: Record<string, unknown> }
  | { type: "error"; content: string }
  | { type: "done" }
  | Record<string, unknown>;

async function parseJsonResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Request failed (${response.status}): ${errorText || response.statusText}`,
    );
  }

  return (await response.json()) as T;
}

export async function createThread(
  userId: string,
): Promise<CreateThreadResponse> {
  const encodedUserId = encodeURIComponent(userId);
  const response = await fetch(
    `${API_BASE_URL}/thread?user_id=${encodedUserId}`,
    {
      method: "POST",
    },
  );

  return parseJsonResponse<CreateThreadResponse>(response);
}

export async function resumeChat(
  request: ResumeRequest,
): Promise<ResumeResponse> {
  const response = await fetch(`${API_BASE_URL}/chat/resume`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(request),
  });

  return parseJsonResponse<ResumeResponse>(response);
}

export async function streamChat(
  request: ChatRequest,
  onEvent: (event: ChatSseEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(request),
    signal,
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(
      `Stream request failed (${response.status}): ${errorText || response.statusText}`,
    );
  }

  if (!response.body) {
    throw new Error("Readable stream is not available in this browser.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split("\n\n");
      buffer = frames.pop() || "";

      for (const frame of frames) {
        const dataLines = frame
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trim());

        if (!dataLines.length) {
          continue;
        }

        const dataString = dataLines.join("\n");

        try {
          const event = JSON.parse(dataString) as ChatSseEvent;
          onEvent(event);
        } catch {
          onEvent({
            type: "error",
            content: `Invalid SSE payload: ${dataString}`,
          });
        }
      }
    }

    // Flush decoder remainder when stream ends.
    const remainder = decoder.decode();
    if (remainder.trim()) {
      buffer += remainder;
    }

    const lastFrame = buffer.trim();
    if (lastFrame.startsWith("data:")) {
      const payload = lastFrame.slice(5).trim();
      try {
        onEvent(JSON.parse(payload) as ChatSseEvent);
      } catch {
        onEvent({ type: "error", content: `Invalid SSE payload: ${payload}` });
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export { API_BASE_URL };
