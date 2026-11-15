# Storytelling TuCaserito (Remotion)

Video (1920×1080, 30 fps) que acompaña la narración en vivo del problema, en dos versiones: 45 s (`media/storytelling-tucaserito.mp4`) y 30 s (`media/storytelling-tucaserito-30s.mp4`).

```bash
npm install
npm run studio   # vista previa interactiva
npm run render      # versión de 45 s
npm run render:30   # versión de 30 s
npm run sfx      # regenera los efectos de sonido (public/sfx)
```

- **Tiempos de cada bloque:** `DURATIONS` en `src/timeline.ts` (en frames, 30 = 1 s), por versión. Las escenas están animadas con la duración `base`; si un bloque dura menos, se acelera en proporción.
- **Volumen de efectos:** `MASTER` en `src/components/Sfx.tsx`.
- **Colores y fuentes:** `src/theme.ts` (marca según `DESIGN.md`).
- Una escena por archivo en `src/scenes/`; Pedro está en `src/components/Pedro.tsx`.
- `node scripts/stills.mjs <carpeta> <frame>...` renderiza fotogramas sueltos para revisar.
