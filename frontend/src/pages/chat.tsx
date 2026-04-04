"use client";

import {
  Attachment,
  AttachmentPreview,
  AttachmentRemove,
  Attachments,
} from "@/components/ai-elements/attachments";
import {
  Confirmation,
  ConfirmationAction,
  ConfirmationActions,
  ConfirmationRequest,
  ConfirmationTitle,
} from "@/components/ai-elements/confirmation";
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from "@/components/ai-elements/conversation";
import {
  Message,
  MessageContent,
  MessageResponse,
} from "@/components/ai-elements/message";
import {
  ModelSelector,
  ModelSelectorContent,
  ModelSelectorEmpty,
  ModelSelectorGroup,
  ModelSelectorInput,
  ModelSelectorItem,
  ModelSelectorList,
  ModelSelectorLogo,
  ModelSelectorLogoGroup,
  ModelSelectorName,
  ModelSelectorTrigger,
} from "@/components/ai-elements/model-selector";
import type { PromptInputMessage } from "@/components/ai-elements/prompt-input";
import {
  PromptInput,
  PromptInputActionAddAttachments,
  PromptInputActionMenu,
  PromptInputActionMenuContent,
  PromptInputActionMenuTrigger,
  PromptInputBody,
  PromptInputButton,
  PromptInputFooter,
  PromptInputHeader,
  PromptInputSubmit,
  PromptInputTextarea,
  PromptInputTools,
  usePromptInputAttachments,
} from "@/components/ai-elements/prompt-input";
import { SpeechInput } from "@/components/ai-elements/speech-input";
import { Shimmer } from "@/components/ai-elements/shimmer";
import { Suggestion, Suggestions } from "@/components/ai-elements/suggestion";
import { Badge } from "@/components/ui/badge";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { FileUIPart } from "ai";
import { CheckIcon, GlobeIcon } from "lucide-react";
import { nanoid } from "nanoid";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import {
  createThread,
  resumeChat,
  streamChat,
  type ChatSseEvent,
} from "../routes/api";

type MessageType = {
  key: string;
  from: "user" | "assistant";
  versions: {
    id: string;
    content: string;
  }[];
};

type PendingInterrupt = {
  details?: Record<string, unknown>;
  node?: string;
};

type GroupedMessage = {
  role: "user" | "assistant";
  agent: "You" | "Agent";
  messages: { id: string; text: string }[];
};

const initialMessages: MessageType[] = [];

const models = [
  {
    chef: "Google",
    chefSlug: "google",
    id: "gemini-2.0-flash-exp",
    name: "Gemini 2.0 Flash",
    providers: ["google"],
  },
  {
    chef: "OpenAI",
    chefSlug: "openai",
    id: "gpt-4o-mini",
    name: "GPT-4o Mini",
    providers: ["openai", "azure"],
  },
];

const chefs = ["Google", "OpenAI"];

const suggestions = [
  "Schedule lunch with Alex tomorrow at 1pm",
  "Check weather in Singapore this evening",
  "Draft an email to my project group",
  "Find my meetings for next Monday",
];

const AttachmentItem = ({
  attachment,
  onRemove,
}: {
  attachment: FileUIPart & { id: string };
  onRemove: (id: string) => void;
}) => {
  const handleRemove = useCallback(() => {
    onRemove(attachment.id);
  }, [onRemove, attachment.id]);

  return (
    <Attachment data={attachment} onRemove={handleRemove}>
      <AttachmentPreview />
      <AttachmentRemove />
    </Attachment>
  );
};

const PromptInputAttachmentsDisplay = () => {
  const attachments = usePromptInputAttachments();

  const handleRemove = useCallback(
    (id: string) => {
      attachments.remove(id);
    },
    [attachments],
  );

  if (attachments.files.length === 0) {
    return null;
  }

  return (
    <Attachments variant="inline">
      {attachments.files.map((attachment) => (
        <AttachmentItem
          attachment={attachment}
          key={attachment.id}
          onRemove={handleRemove}
        />
      ))}
    </Attachments>
  );
};

const SuggestionItem = ({
  suggestion,
  onClick,
}: {
  suggestion: string;
  onClick: (suggestion: string) => void;
}) => {
  const handleClick = useCallback(() => {
    onClick(suggestion);
  }, [onClick, suggestion]);

  return <Suggestion onClick={handleClick} suggestion={suggestion} />;
};

const ModelItem = ({
  m,
  isSelected,
  onSelect,
}: {
  m: (typeof models)[0];
  isSelected: boolean;
  onSelect: (id: string) => void;
}) => {
  const handleSelect = useCallback(() => {
    onSelect(m.id);
  }, [onSelect, m.id]);

  return (
    <ModelSelectorItem onSelect={handleSelect} value={m.id}>
      <ModelSelectorLogo provider={m.chefSlug} />
      <ModelSelectorName>{m.name}</ModelSelectorName>
      <ModelSelectorLogoGroup>
        {m.providers.map((provider) => (
          <ModelSelectorLogo key={provider} provider={provider} />
        ))}
      </ModelSelectorLogoGroup>
      {isSelected ? (
        <CheckIcon className="ml-auto size-4" />
      ) : (
        <div className="ml-auto size-4" />
      )}
    </ModelSelectorItem>
  );
};

const Chat = () => {
  const [model, setModel] = useState<string>(models[0].id);
  const [modelSelectorOpen, setModelSelectorOpen] = useState(false);
  const [text, setText] = useState<string>("");
  const [useWebSearch, setUseWebSearch] = useState<boolean>(false);
  const [status, setStatus] = useState<
    "submitted" | "streaming" | "ready" | "error"
  >("ready");
  const [messages, setMessages] = useState<MessageType[]>(initialMessages);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [userId] = useState<string>(`web_${nanoid(8)}`);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [routedTo, setRoutedTo] = useState<string | null>(null);
  const [agentTrace, setAgentTrace] = useState<string[]>([]);
  const [pendingInterrupt, setPendingInterrupt] =
    useState<PendingInterrupt | null>(null);
  const [currentAssistantMessageId, setCurrentAssistantMessageId] = useState<
    string | null
  >(null);

  const streamAbortRef = useRef<AbortController | null>(null);
  const currentAssistantMessageIdRef = useRef<string | null>(null);
  const activeNodeRef = useRef<string | null>(null);
  const onboardingShownRef = useRef(false);

  const selectedModelData = useMemo(
    () => models.find((m) => m.id === model),
    [model],
  );

  const appendMessage = useCallback((message: MessageType) => {
    setMessages((prev) => [...prev, message]);
  }, []);

  const maybeShowOnboarding = useCallback(
    (onboardingMessage?: string | null) => {
      if (!onboardingMessage || onboardingShownRef.current) {
        return;
      }

      appendMessage({
        from: "assistant",
        key: nanoid(),
        versions: [
          {
            id: nanoid(),
            content: onboardingMessage,
          },
        ],
      });
      onboardingShownRef.current = true;
    },
    [appendMessage],
  );

  const appendMessageChunk = useCallback((messageId: string, chunk: string) => {
    setMessages((prev) =>
      prev.map((msg) => {
        if (!msg.versions.some((v) => v.id === messageId)) {
          return msg;
        }

        return {
          ...msg,
          versions: msg.versions.map((v) =>
            v.id === messageId
              ? {
                  ...v,
                  content: v.content ? `${v.content}\n\n${chunk}` : chunk,
                }
              : v,
          ),
        };
      }),
    );
  }, []);

  const ensureThread = useCallback(async (): Promise<string> => {
    if (threadId) {
      return threadId;
    }

    const created = await createThread(userId);
    maybeShowOnboarding(created.onboarding_message);
    setThreadId(created.thread_id);
    return created.thread_id;
  }, [threadId, userId, maybeShowOnboarding]);

  useEffect(() => {
    let mounted = true;

    const init = async () => {
      try {
        const created = await createThread(userId);
        if (!mounted) {
          return;
        }
        maybeShowOnboarding(created.onboarding_message);
        setThreadId(created.thread_id);
        toast.success("Chat thread ready", {
          description: `Thread: ${created.thread_id.slice(0, 8)}...`,
        });
      } catch (error) {
        if (!mounted) {
          return;
        }
        setStatus("error");
        toast.error("Unable to create chat thread", {
          description:
            error instanceof Error
              ? error.message
              : "Backend is not reachable.",
        });
      }
    };

    void init();

    return () => {
      mounted = false;
      streamAbortRef.current?.abort();
    };
  }, [userId, maybeShowOnboarding]);

  useEffect(() => {
    currentAssistantMessageIdRef.current = currentAssistantMessageId;
  }, [currentAssistantMessageId]);

  useEffect(() => {
    activeNodeRef.current = activeNode;
  }, [activeNode]);

  const handleStreamEvent = useCallback(
    (event: ChatSseEvent) => {
      const activeAssistantId = currentAssistantMessageIdRef.current;

      const eventType = typeof event.type === "string" ? event.type : "unknown";

      if (
        eventType === "node" &&
        typeof (event as { node?: unknown }).node === "string"
      ) {
        const nextNode = (event as { node: string }).node;
        activeNodeRef.current = nextNode;
        setActiveNode(nextNode);
        setAgentTrace((prev) =>
          prev[prev.length - 1] === nextNode ? prev : [...prev, nextNode],
        );
        return;
      }

      if (
        eventType === "route" &&
        typeof (event as { to?: unknown }).to === "string"
      ) {
        const target = (event as { to: string }).to;
        setRoutedTo(target);
        toast.message("Routing", { description: `Routed to ${target}` });
        return;
      }

      if (
        eventType === "message" &&
        typeof (event as { content?: unknown }).content === "string"
      ) {
        if (!activeAssistantId) {
          return;
        }
        const nextContent = (event as { content: string }).content;
        appendMessageChunk(activeAssistantId, nextContent);
        return;
      }

      if (eventType === "interrupt") {
        const details =
          typeof (event as { details?: unknown }).details === "object" &&
          (event as { details?: unknown }).details !== null
            ? ((event as { details?: Record<string, unknown> }).details ??
              undefined)
            : undefined;
        setPendingInterrupt({
          details,
          node: activeNodeRef.current ?? undefined,
        });
        toast.info("Approval required", {
          description: "The agent is waiting for approve/reject to continue.",
        });
        return;
      }

      if (
        eventType === "error" &&
        typeof (event as { content?: unknown }).content === "string"
      ) {
        setStatus("error");
        toast.error("Stream error", {
          description: (event as { content: string }).content,
        });
        return;
      }

      if (eventType === "done") {
        setStatus("ready");
        setActiveNode(null);
        setCurrentAssistantMessageId(null);
        currentAssistantMessageIdRef.current = null;
        activeNodeRef.current = null;
      }
    },
    [appendMessageChunk],
  );

  const sendToBackend = useCallback(
    async (content: string) => {
      setStatus("submitted");
      setPendingInterrupt(null);

      const currentThreadId = await ensureThread();
      setAgentTrace([]);
      setRoutedTo(null);

      const userMessage: MessageType = {
        from: "user",
        key: `user-${Date.now()}`,
        versions: [{ content, id: `user-${Date.now()}` }],
      };
      appendMessage(userMessage);

      const assistantMessageId = `assistant-${Date.now()}`;
      const assistantMessage: MessageType = {
        from: "assistant",
        key: `assistant-${Date.now()}`,
        versions: [{ content: "", id: assistantMessageId }],
      };
      appendMessage(assistantMessage);
      setCurrentAssistantMessageId(assistantMessageId);
      currentAssistantMessageIdRef.current = assistantMessageId;
      setStatus("streaming");

      streamAbortRef.current?.abort();
      const controller = new AbortController();
      streamAbortRef.current = controller;

      try {
        await streamChat(
          {
            thread_id: currentThreadId,
            user_id: userId,
            message: content,
          },
          handleStreamEvent,
          controller.signal,
        );
      } catch (error) {
        setStatus("error");
        toast.error("Failed to stream chat", {
          description: error instanceof Error ? error.message : "Unknown error",
        });
      } finally {
        setStatus((prev) => (prev === "error" ? "error" : "ready"));
      }
    },
    [appendMessage, ensureThread, handleStreamEvent, userId],
  );

  const handleSubmit = useCallback(
    (message: PromptInputMessage) => {
      const textValue = message.text?.trim() ?? "";
      const hasAttachments = Boolean(message.files?.length);

      if (!(textValue || hasAttachments)) {
        return;
      }

      if (hasAttachments) {
        toast.warning("Attachments are not sent yet", {
          description: "Current backend endpoint only accepts text messages.",
        });
      }

      setText("");
      void sendToBackend(textValue || "Sent with attachments");
    },
    [sendToBackend],
  );

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      void sendToBackend(suggestion);
    },
    [sendToBackend],
  );

  const handleInterruptDecision = useCallback(
    async (decision: "approve" | "reject") => {
      if (!threadId || status === "streaming") {
        return;
      }

      const previousInterrupt = pendingInterrupt;
      setPendingInterrupt(null);
      setStatus("submitted");

      try {
        const response = await resumeChat({
          thread_id: threadId,
          user_id: userId,
          decision,
        });

        const assistantMessage: MessageType = {
          from: "assistant",
          key: `assistant-resume-${Date.now()}`,
          versions: [
            { id: `assistant-resume-${Date.now()}`, content: response.reply },
          ],
        };
        appendMessage(assistantMessage);
        setStatus("ready");
      } catch (error) {
        setPendingInterrupt(previousInterrupt);
        setStatus("error");
        toast.error("Resume failed", {
          description: error instanceof Error ? error.message : "Unknown error",
        });
      }
    },
    [appendMessage, pendingInterrupt, status, threadId, userId],
  );

  const handleTranscriptionChange = useCallback((transcript: string) => {
    setText((prev) => (prev ? `${prev} ${transcript}` : transcript));
  }, []);

  const handleTextChange = useCallback(
    (event: React.ChangeEvent<HTMLTextAreaElement>) => {
      setText(event.target.value);
    },
    [],
  );

  const toggleWebSearch = useCallback(() => {
    setUseWebSearch((prev) => !prev);
    toast.message("Web search toggle", {
      description:
        "UI only for now. Backend routing currently ignores this flag.",
    });
  }, []);

  const handleModelSelect = useCallback((modelId: string) => {
    setModel(modelId);
    setModelSelectorOpen(false);
  }, []);

  const stopStreaming = useCallback(() => {
    streamAbortRef.current?.abort();
    setStatus("ready");
    setActiveNode(null);
    setCurrentAssistantMessageId(null);
    currentAssistantMessageIdRef.current = null;
    activeNodeRef.current = null;
  }, []);

  const isSubmitDisabled = useMemo(
    () => !(text.trim().length > 0) || status === "streaming",
    [text, status],
  );

  const isChatInputBlocked = useMemo(
    () => Boolean(pendingInterrupt) || status === "streaming",
    [pendingInterrupt, status],
  );

  const groupedMessages = useMemo<GroupedMessage[]>(() => {
    const rows = messages.flatMap((message) =>
      message.versions.map((version) => ({
        id: version.id,
        role: message.from,
        text: version.content,
      })),
    );

    return rows.reduce<GroupedMessage[]>((acc, row) => {
      const last = acc[acc.length - 1];
      if (last && last.role === row.role) {
        last.messages.push({ id: row.id, text: row.text });
        return acc;
      }

      acc.push({
        role: row.role,
        agent: row.role === "user" ? "You" : "Agent",
        messages: [{ id: row.id, text: row.text }],
      });
      return acc;
    }, []);
  }, [messages]);

  const confirmationApproval = useMemo(
    () =>
      pendingInterrupt
        ? {
            id: `${threadId ?? "thread"}-${pendingInterrupt.node ?? "approval"}`,
          }
        : undefined,
    [pendingInterrupt, threadId],
  );

  return (
    <TooltipProvider>
      <div className="h-svh w-full bg-linear-to-b from-muted/50 via-background to-background">
        <div className="mx-auto flex h-full w-full max-w-6xl flex-col gap-4 px-3 py-4 md:px-6 md:py-6">
          <header className="flex flex-wrap items-center justify-between gap-3 rounded-xl border bg-card/80 px-4 py-3 backdrop-blur-sm">
            <div className="space-y-1 text-left">
              <h2 className="font-semibold text-foreground text-lg">
                Personal Assistant APP
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={threadId ? "secondary" : "outline"}>
                {threadId
                  ? `Thread: ${threadId.slice(0, 8)}...`
                  : "Creating thread"}
              </Badge>
              {/* <Badge
                variant={
                  status === "error"
                    ? "destructive"
                    : status === "streaming"
                      ? "default"
                      : "outline"
                }
              >
                Status: {status} */}
              {/* </Badge>
              {activeNode ? (
                <Badge variant="outline">Node: {activeNode}</Badge>
              ) : null}
              {routedTo ? (
                <Badge variant="outline">Routed: {routedTo}</Badge>
              ) : null}
              {agentTrace.length > 0 ? (
                <Badge variant="outline">
                  Agents: {agentTrace.join(" -> ")}
                </Badge>
              ) : null} */}
            </div>
          </header>

          <Confirmation
            approval={confirmationApproval}
            className="rounded-xl border-amber-500/40 bg-amber-500/10 text-left"
            state="approval-requested"
          >
            <ConfirmationRequest>
              <ConfirmationTitle className="font-medium text-sm">
                Agent requires a decision
              </ConfirmationTitle>
              <p className="mt-1 text-muted-foreground text-sm">
                Current node: {pendingInterrupt?.node ?? "Unknown"}
              </p>
              <ConfirmationActions className="mt-3">
                <ConfirmationAction
                  disabled={status === "streaming"}
                  onClick={() => {
                    void handleInterruptDecision("approve");
                  }}
                >
                  Approves
                </ConfirmationAction>
                <ConfirmationAction
                  disabled={status === "streaming"}
                  onClick={() => {
                    void handleInterruptDecision("reject");
                  }}
                  variant="outline"
                >
                  Reject
                </ConfirmationAction>
              </ConfirmationActions>
            </ConfirmationRequest>
          </Confirmation>

          <section className="relative flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border bg-card shadow-sm">
            <Conversation className="h-full">
              <ConversationContent className="gap-10 md:p-8">
                {groupedMessages.map((group, index) => (
                  <Message
                    from={group.role}
                    key={`${group.role}-${index}-${group.messages[0]?.id ?? index}`}
                  >
                    <span
                      className={
                        group.role === "user"
                          ? "self-end text-muted-foreground text-xs uppercase tracking-wide"
                          : "self-start text-muted-foreground text-xs uppercase tracking-wide"
                      }
                    >
                      {group.agent}
                    </span>
                    {group.messages.map((entry) => {
                      const hasText = entry.text.trim().length > 0;
                      const isActiveAssistantEntry =
                        group.role === "assistant" &&
                        entry.id === currentAssistantMessageId;
                      const showStreamingPlaceholder =
                        isActiveAssistantEntry &&
                        (status === "submitted" || status === "streaming");
                      const showApprovalPlaceholder =
                        isActiveAssistantEntry &&
                        Boolean(pendingInterrupt) &&
                        status === "ready";

                      if (
                        !hasText &&
                        !showStreamingPlaceholder &&
                        !showApprovalPlaceholder
                      ) {
                        return null;
                      }

                      return (
                        <MessageContent
                          className={
                            group.role === "assistant"
                              ? "rounded-xl border border-border/80 bg-background/70 px-4 py-3 shadow-sm"
                              : undefined
                          }
                          key={entry.id}
                        >
                          {hasText ? (
                            <MessageResponse>{entry.text}</MessageResponse>
                          ) : showStreamingPlaceholder ? (
                            <div className="flex justify-center">
                              <Shimmer className="text-base font-medium">
                                Crafting Response
                              </Shimmer>
                            </div>
                          ) : (
                            <div className="text-muted-foreground text-sm">
                              Waiting for approval...
                            </div>
                          )}
                        </MessageContent>
                      );
                    })}
                  </Message>
                ))}
              </ConversationContent>
              <ConversationScrollButton />
            </Conversation>

            {(status === "submitted" || status === "streaming") &&
            (routedTo || activeNode) ? (
              <div className="pointer-events-none absolute inset-x-0 bottom-4 z-10 flex justify-center px-4">
                <div className="rounded-full border border-border/80 bg-background/85 px-4 py-2 shadow-sm backdrop-blur-sm">
                  <div className="flex items-center gap-2 text-sm">
                    <span className="text-muted-foreground">Routing:</span>
                    <Shimmer className="text-sm font-medium">
                      {(routedTo ?? activeNode ?? "orchestrator").replaceAll(
                        "_",
                        " ",
                      )}
                    </Shimmer>
                  </div>
                </div>
              </div>
            ) : null}
          </section>

          <section className="space-y-3 rounded-2xl border bg-background/90 p-3 md:p-4">
            <Suggestions>
              {suggestions.map((item) => (
                <SuggestionItem
                  key={item}
                  onClick={handleSuggestionClick}
                  suggestion={item}
                />
              ))}
            </Suggestions>

            <PromptInput onSubmit={handleSubmit}>
              <PromptInputHeader>
                <PromptInputAttachmentsDisplay />
              </PromptInputHeader>

              <PromptInputBody>
                <PromptInputTextarea
                  disabled={isChatInputBlocked}
                  onChange={handleTextChange}
                  placeholder={
                    isChatInputBlocked
                      ? "Wait for approval or current response to finish..."
                      : "Ask your assistant about calendar, email, or weather..."
                  }
                  value={text}
                />
              </PromptInputBody>

              <PromptInputFooter>
                <PromptInputTools>
                  <PromptInputActionMenu>
                    <PromptInputActionMenuTrigger tooltip="More actions" />
                    <PromptInputActionMenuContent>
                      <PromptInputActionAddAttachments />
                    </PromptInputActionMenuContent>
                  </PromptInputActionMenu>

                  <PromptInputButton
                    onClick={toggleWebSearch}
                    tooltip="Toggle web search hint"
                    variant={useWebSearch ? "default" : "ghost"}
                  >
                    <GlobeIcon className="size-4" />
                  </PromptInputButton>

                  <ModelSelector
                    onOpenChange={setModelSelectorOpen}
                    open={modelSelectorOpen}
                  >
                    <ModelSelectorTrigger asChild>
                      <PromptInputButton
                        className="w-48"
                        size="sm"
                        variant="outline"
                      >
                        <span className="truncate">
                          {selectedModelData?.name ?? "Select model"}
                        </span>
                      </PromptInputButton>
                    </ModelSelectorTrigger>
                    <ModelSelectorContent>
                      <ModelSelectorInput placeholder="Search model..." />
                      <ModelSelectorList>
                        <ModelSelectorEmpty>No model found.</ModelSelectorEmpty>
                        {chefs.map((chef) => (
                          <ModelSelectorGroup heading={chef} key={chef}>
                            {models
                              .filter((m) => m.chef === chef)
                              .map((m) => (
                                <ModelItem
                                  isSelected={model === m.id}
                                  key={m.id}
                                  m={m}
                                  onSelect={handleModelSelect}
                                />
                              ))}
                          </ModelSelectorGroup>
                        ))}
                      </ModelSelectorList>
                    </ModelSelectorContent>
                  </ModelSelector>
                </PromptInputTools>

                <PromptInputTools>
                  <SpeechInput
                    disabled={isChatInputBlocked}
                    onTranscriptionChange={handleTranscriptionChange}
                  />
                  <PromptInputSubmit
                    disabled={isSubmitDisabled || isChatInputBlocked}
                    onStop={stopStreaming}
                    status={status}
                  />
                </PromptInputTools>
              </PromptInputFooter>
            </PromptInput>
          </section>
        </div>
      </div>
    </TooltipProvider>
  );
};

export default Chat;
