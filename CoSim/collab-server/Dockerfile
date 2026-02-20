# Yjs Collaboration Server for CoSim
# Provides WebSocket-based CRDT synchronization for real-time collaborative editing

FROM node:20-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --production

# Copy server code
COPY *.js ./

# Create data directory for persistence (optional)
RUN mkdir -p /data

EXPOSE 1234

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD node -e "require('http').get('http://localhost:1234/health', (r) => { process.exit(r.statusCode === 200 ? 0 : 1) })"

CMD ["node", "server.js"]
