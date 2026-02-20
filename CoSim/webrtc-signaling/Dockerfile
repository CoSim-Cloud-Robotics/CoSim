FROM node:18-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm install --production

# Copy server code
COPY *.js ./

# Expose WebSocket port and health check port
EXPOSE 3000 3001

# Run server
CMD ["npm", "start"]
