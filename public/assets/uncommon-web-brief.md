# Canvas UI — ASCII lens over live HTML

> WebGL effects that post-process real, interactive HTML

- section: kits  ·  framework: react  ·  tags: webgl, html-in-canvas, shader
- meta: MIT + Commons Clause · vregistry (fetched 2026-10-22)
- entry page: https://webdev.teknium.io/d/canvasui-asciify-lens/
- live demo: https://webdev.teknium.io/d/kits3/demos/canvasui-asciify-lens/
- catalog source: https://webdev.teknium.io/ (Uncommon Web field guide)

## Install

```
npx shadcn@latest add https://canvasui.dev/r/asciify-react.json
```

_registry add (shadcn-style): writes real source files into your project, usually with a paths prompt_

## Usage (site's own snippet)

```
<Asciify
  charset={charset}          // "ascii" | "blocks" | "binary"
  radius={radius}            // lens radius, fraction of height
  softness={0.3}
  scale={3}
  background={BG}
  backgroundOpacity={0.6}
  brightness={0.3}
  glow={0.8}
>
  <main className="page">{/* real, clickable HTML */}</main>
</Asciify>
```

## Blurb

Canvas UI components wrap ordinary HTML and run it through a WebGL shader, using Chrome's experimental HTML-in-Canvas API (drawElementImage) so the content stays clickable while it is being rendered as pixels. Here <Asciify> turns a space-weather dashboard into colored 5x5 glyphs inside a drifting lens; the tabs and buttons underneath still work. Browsers without the API get the library's own DOM-snapshot fallback; the badge shows which path is running.

## Links

- site ↗: https://canvasui.dev
- source ↗: https://github.com/DavidHDev/canvas-ui
