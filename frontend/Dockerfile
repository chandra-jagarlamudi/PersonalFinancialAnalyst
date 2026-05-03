FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host needed so port publish works from the host (Compose).
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
