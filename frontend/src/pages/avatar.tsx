import { useEffect, useRef, useState } from "react";

type TalkingHeadInstance = {
  showAvatar: (
    options: Record<string, unknown>,
    onProgress?: (event: ProgressEvent<EventTarget>) => void,
  ) => Promise<void>;
  speakText: (text: string) => void;
  start: () => void;
  stop: () => void;
};

const Avatar = () => {
  const avatarRef = useRef<HTMLDivElement | null>(null);
  const headRef = useRef<TalkingHeadInstance | null>(null);
  const [loadingText, setLoadingText] = useState("Loading...");
  const [text, setText] = useState("Hi there. How are you? I'm fine.");

  useEffect(() => {
    let mounted = true;

    const bootstrap = async () => {
      if (!avatarRef.current) {
        return;
      }

      try {
        const { TalkingHead } = await import("@met4citizen/talkinghead");
        if (!mounted || !avatarRef.current) {
          return;
        }

        const head = new TalkingHead(avatarRef.current, {
          cameraView: "upper",
          lipsyncModules: ["en", "fi"],
          ttsApikey: "put-your-own-Google-TTS-API-key-here",
          ttsEndpoint:
            "https://eu-texttospeech.googleapis.com/v1beta1/text:synthesize",
        }) as TalkingHeadInstance;

        headRef.current = head;

        const avatarUrl = new URL("../avatars/brunette-t.glb", import.meta.url)
          .href;

        const avatarResponse = await fetch(avatarUrl, { method: "GET" });
        if (!avatarResponse.ok) {
          throw new Error(
            `Avatar not found at ${avatarUrl} (HTTP ${avatarResponse.status})`,
          );
        }

        await head.showAvatar(
          {
            avatarMood: "neutral",
            baseline: {
              eyeBlinkLeft: 0.15,
              eyeBlinkRight: 0.15,
              headRotateX: -0.05,
            },
            body: "F",
            lipsyncLang: "en",
            ttsLang: "en-GB",
            ttsVoice: "en-GB-Standard-A",
            url: avatarUrl,
          },
          (ev) => {
            if (!mounted) {
              return;
            }

            if (ev.lengthComputable) {
              const val = Math.min(
                100,
                Math.round((ev.loaded / ev.total) * 100),
              );
              setLoadingText(`Loading ${val}%`);
            }
          },
        );

        if (mounted) {
          setLoadingText("");
        }
      } catch (error) {
        if (mounted) {
          setLoadingText(
            error instanceof Error ? error.message : String(error),
          );
        }
      }
    };

    const onVisibility = () => {
      if (!headRef.current) {
        return;
      }
      if (document.visibilityState === "visible") {
        headRef.current.start();
      } else {
        headRef.current.stop();
      }
    };

    void bootstrap();
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      mounted = false;
      document.removeEventListener("visibilitychange", onVisibility);
      headRef.current?.stop();
      headRef.current = null;
    };
  }, []);

  const handleSpeak = () => {
    if (!text.trim() || !headRef.current) {
      return;
    }
    headRef.current.speakText(text);
  };

  return (
    <div className="relative mx-auto h-full w-full max-w-5xl overflow-hidden rounded-xl bg-zinc-900 text-white">
      <div className="h-full w-full" ref={avatarRef} />

      <div className="absolute top-3 right-3 left-3 flex items-center gap-2">
        <input
          className="h-11 w-full rounded-md border border-white/20 bg-black/40 px-3 text-base outline-none"
          onChange={(event) => {
            setText(event.target.value);
          }}
          type="text"
          value={text}
        />
        <button
          className="h-11 rounded-md bg-white px-4 font-medium text-black"
          onClick={handleSpeak}
          type="button"
        >
          Speak
        </button>
      </div>

      {loadingText ? (
        <div className="absolute right-3 bottom-3 left-3 rounded-md bg-black/60 px-3 py-2 text-sm">
          {loadingText}
        </div>
      ) : null}
    </div>
  );
};

export default Avatar;
