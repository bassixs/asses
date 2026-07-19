import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

/**
 * Страховка от невидимого контента.
 *
 * Блоки появляются анимацией, которая стартует с opacity 0 (animation-fill-mode:
 * backwards). Если таймлайн анимаций не идёт — вкладка не отрисовывается, движок
 * их заморозил — блоки навсегда останутся прозрачными, и человек увидит пустую
 * страницу. Проверяем один раз: если анимации есть, но их время стоит на нуле,
 * выключаем появление совсем — контент важнее эффекта.
 */
setTimeout(() => {
  const animations = document.getAnimations?.() ?? [];
  const frozen = animations.length > 0 && animations.every((a) => !a.currentTime);
  if (frozen) document.documentElement.classList.add("no-anim");
}, 1500);
