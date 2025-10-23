import Link from 'next/link';

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gray-50">
      <div className="text-center space-y-6 px-4">
        <h1 className="text-6xl font-bold text-purple-600">
          LFG 🚀
        </h1>
        <p className="text-xl text-gray-600 max-w-md mx-auto">
          AI-Powered Product Development Platform
        </p>
        <div className="flex gap-4 justify-center mt-8">
          <Link
            href="/auth"
            className="px-6 py-3 bg-purple-600 text-white rounded-lg font-medium hover:bg-purple-700 transition-colors"
          >
            Get Started
          </Link>
          <Link
            href="/projects"
            className="px-6 py-3 bg-white text-purple-600 border border-purple-200 rounded-lg font-medium hover:bg-purple-50 transition-colors"
          >
            View Projects
          </Link>
        </div>
      </div>
    </div>
  );
}
