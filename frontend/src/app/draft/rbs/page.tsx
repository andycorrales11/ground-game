import GenericDataTable from '@/app/components/GenericDataTable';
import Header from '@/app/components/Header';

export default function HomePage() {
  return (
    <main className="p-8">
      <Header />
      <GenericDataTable 
        endpoint="/api/players/rbs?limit=100" 
        title="2024 RB Stats" 
      />
    </main>
  );
}
