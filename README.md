# Maxis AI Agency

Nexus Agent Command Center: three agent chats, Agent Council group chat, alerts, shared memory, supervision controls, connector hub, and responsive mobile UI.

## Live site

https://1c47df37.nexus-agent-command-center.pages.dev

## Source

The dashboard source is under `apps/llama-agent-command-center`. It uses the Llama connection through the Tasklet host bridge; credentials are never stored in this repository.

## Deployment

The UI is deployed to Cloudflare Pages with a direct upload. The public static site can be used as the visual dashboard. Full agent tool calls require the Tasklet host bridge or a secured backend/Worker endpoint; do not place Llama, GitHub, Telegram, or Cloudflare secrets in browser code.