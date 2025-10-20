# LFG Frontend - Next.js UI

A clean, light-themed Next.js implementation of the LFG UI.

## Features

- ✅ **Authentication Pages** - Login/Register with Google OAuth support
- ✅ **Projects Listing** - View and manage all your projects
- ✅ **Chat Interface** - Real-time chat with AI assistants
- ✅ **Artifacts Panel** - Document and task management sidebar
- ✅ **Settings** - Profile, integrations, API keys, and subscription management
- ✅ **Light Theme** - Clean, modern UI with purple/blue gradients

## Getting Started

### Install Dependencies

```bash
npm install
```

### Run Development Server

```bash
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) to view the app.

### Build for Production

```bash
npm run build
npm start
```

## Project Structure

```
frontend/
├── app/                    # Next.js app directory
│   ├── auth/              # Authentication pages
│   ├── chat/              # Chat interface
│   ├── projects/          # Projects listing
│   ├── settings/          # Settings page
│   ├── layout.tsx         # Root layout
│   ├── page.tsx           # Home page
│   └── globals.css        # Global styles
├── components/            # Reusable components
│   ├── Sidebar.tsx        # Navigation sidebar
│   └── ArtifactsPanel.tsx # Documents/tasks panel
└── public/               # Static assets
```

## Pages

### Authentication (`/auth`)
- Login and register tabs
- Email/password and Google OAuth
- Light-themed with animated background

### Projects (`/projects`)
- List all projects with stats
- Create new projects
- Quick access to conversations, documents, tickets

### Chat (`/chat`)
- Real-time messaging interface
- Toggle artifacts panel
- Model and role selection
- File upload support

### Settings (`/settings`)
- Profile management
- Integrations (GitHub, Linear, Notion)
- API keys configuration
- Subscription details

## Tech Stack

- **Next.js 15** - React framework
- **TypeScript** - Type safety
- **Tailwind CSS** - Utility-first styling
- **React 19** - UI library

## Customization

### Colors
Update `tailwind.config.ts` to change the color scheme:

```typescript
colors: {
  primary: {
    // Your custom colors
  }
}
```

### Global Styles
Modify `app/globals.css` for global theme variables.

## Notes

- All data is currently dummy/static
- WebSocket connections need backend integration
- File uploads need backend API endpoints
- OAuth flows need backend authentication setup
