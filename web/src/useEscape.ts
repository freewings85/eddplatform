import { useEffect } from "react";

/** 弹窗按 Esc 关闭（点击遮罩不关闭——防误点丢表单）。 */
export function useEscape(onEscape: () => void) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onEscape();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [onEscape]);
}
