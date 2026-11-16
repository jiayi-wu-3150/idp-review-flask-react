import { ReviewPage } from './review/ReviewPage';

export default function App() {
  return (
    <div className="min-h-screen bg-neutral-950">
      <header className="border-b border-neutral-800 px-6 py-3">
        <h1 className="text-lg font-semibold">Intelligent Document Review</h1>
      </header>
      <main className="p-6">
        <ReviewPage />
      </main>
    </div>
  );
}
