FROM node:20-alpine
WORKDIR /app

# Copy dependency manifests (context is already the frontend folder)
COPY package.json package-lock.json* ./
RUN npm install --legacy-peer-deps || true

# Copy source code
COPY . .

RUN npm run build
EXPOSE 3000
CMD ["npm", "run", "start"]
