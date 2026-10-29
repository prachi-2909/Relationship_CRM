# Claude bridge: the Claude CLI behind a small OpenAI-compatible endpoint (see server.js).
# Internal to the compose network; the CLI's login lives in the claude-auth volume, never in the image.
FROM node:22-slim

RUN npm install -g @anthropic-ai/claude-code \
    && npm cache clean --force \
    && mkdir -p /home/node/.claude /home/node/work \
    && chown -R node:node /home/node

USER node
WORKDIR /home/node/work
COPY --chown=node:node server.js /home/node/server.js

ENV PORT=8080 \
    CLAUDE_WORKDIR=/home/node/work

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:8080/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"

CMD ["node", "/home/node/server.js"]
