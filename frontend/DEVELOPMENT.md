# Frontend - Local Development Setup

## 🚀 Quick Start for Development

### Option 1: Using Docker (Recommended)

This setup uses bind mounts, so code changes are reflected immediately with Hot Module Replacement (HMR).

```bash
# Start frontend in development mode
docker-compose up

# Frontend will auto-reload on code changes
# Access at: http://localhost:3000
```

**How it works:**
- Uses `Dockerfile.dev` with Vite dev server
- Bind mounts your local code (`./` → `/app`)
- Vite HMR updates browser instantly on file changes
- Node modules cached in container volume
- No need to rebuild after code changes

### Option 2: Local Node.js (Without Docker)

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Access at: http://localhost:3000
```

## 📝 Development Workflow

### 1. Start Services
```bash
docker-compose up
```

### 2. Make Code Changes
- Edit any React/JS/CSS file
- Vite HMR updates browser instantly
- No page refresh needed for most changes
- No rebuild needed!

### 3. View Logs
```bash
docker-compose logs -f frontend
```

### 4. Access Application
- Frontend: http://localhost:3000
- Auto-opens in browser with HMR enabled

### 5. Stop Services
```bash
docker-compose down
```

## 🔧 Useful Commands

```bash
# Rebuild only if package.json changes
docker-compose build frontend

# Install new package (in running container)
docker-compose exec frontend npm install <package-name>

# Or rebuild after adding to package.json
docker-compose down
docker-compose build frontend
docker-compose up

# Execute commands in running container
docker-compose exec frontend npm run lint

# Access container shell
docker-compose exec frontend sh

# View frontend logs only
docker-compose logs -f frontend

# Clear node_modules cache (if needed)
docker-compose down -v
docker-compose build --no-cache frontend
docker-compose up
```

## 📦 What Gets Mounted

```yaml
volumes:
  - .:/app                    # Your code (hot reload with HMR)
  - /app/node_modules         # Keep node_modules in container
```

The `/app/node_modules` anonymous volume prevents the host's node_modules from overriding the container's, ensuring consistent dependencies.

## 🔄 When to Rebuild

You only need to rebuild when:
- ✅ `package.json` changes (new dependencies)
- ✅ `vite.config.js` changes
- ✅ `Dockerfile.dev` changes
- ❌ NOT when JS/JSX/CSS changes (HMR handles it)
- ❌ NOT when adding new components

## ⚡ Vite HMR Features

Vite provides instant updates for:
- React components (preserves state)
- CSS/styles
- Static assets
- Most code changes without full reload

Look for this in logs:
```
VITE v5.0.8  ready in X ms

➜  Local:   http://localhost:3000/
➜  Network: http://172.x.x.x:3000/
➜  press h + enter to show help
```

## 🐛 Debugging

### View all logs
```bash
docker-compose logs -f
```

### Check if HMR is working
After saving a file, you should see:
```
[vite] hot updated: /src/App.jsx
```

### HMR not working?
1. Check browser console for HMR connection
2. Ensure port 3000 is accessible
3. Try hard refresh (Cmd+Shift+R or Ctrl+Shift+R)
4. Restart container: `docker-compose restart frontend`

### Attach to running container
```bash
docker attach voiceai-frontend
```

### Clean start
```bash
docker-compose down
docker-compose build --no-cache frontend
docker-compose up
```

## 🎨 Development Tips

### Environment Variables
- Must be prefixed with `VITE_`
- Defined in `.env` file
- Access with `import.meta.env.VITE_API_URL`
- Changes require server restart

### Hot Reload Scope
- ✅ Component changes → instant
- ✅ CSS changes → instant
- ✅ Hook changes → instant
- ⚠️ Config changes → restart needed
- ⚠️ .env changes → restart needed
