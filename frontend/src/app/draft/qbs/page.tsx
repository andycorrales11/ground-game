import GenericDataTable from '@/app/components/GenericDataTable';

export default function HomePage() {
  return (
    <main className="p-8">
      <GenericDataTable 
        endpoint="/api/players/qbs?limit=100" 
        title="2024 QB Stats" 
      />
    </main>
  );
}
