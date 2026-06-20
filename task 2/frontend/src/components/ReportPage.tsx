import React, { useState } from 'react';
import { useKeycloak } from '@react-keycloak/web';

interface DailyStat {
  report_date: string;
  total_movements: number;
  avg_response_ms: number;
  battery_drain_pct: number;
  session_count: number;
  firmware_version: string;
}

interface ReportData {
  user_id: number;
  period: { start: string; end: string };
  daily_stats: DailyStat[];
  summary: {
    total_movements: number;
    avg_response_ms: number;
    total_days: number;
  };
}

const ReportPage: React.FC = () => {
  const { keycloak, initialized } = useKeycloak();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [startDate, setStartDate] = useState<string>(
    new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10)
  );
  const [endDate, setEndDate] = useState<string>(
    new Date().toISOString().slice(0, 10)
  );

  const fetchReport = async () => {
    if (!keycloak?.token) {
      setError('Not authenticated');
      return;
    }

    if (!startDate || !endDate) {
      setError('Please select both start and end dates');
      return;
    }

    try {
      setLoading(true);
      setError(null);

      const params = new URLSearchParams({
        start_date: startDate,
        end_date: endDate,
      });

      const response = await fetch(
        `${process.env.REACT_APP_API_URL}/reports?${params.toString()}`,
        {
          headers: {
            Authorization: `Bearer ${keycloak.token}`,
          },
        }
      );

      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          throw new Error('You are not authorized to view this report');
        } else if (response.status === 400) {
          const text = await response.text();
          throw new Error(`Invalid request: ${text}`);
        } else if (response.status === 404) {
          throw new Error('No data found for the selected period');
        } else {
          throw new Error(`Server error: ${response.status}`);
        }
      }

      const data: ReportData = await response.json();
      setReportData(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An error occurred');
      setReportData(null);
    } finally {
      setLoading(false);
    }
  };

  const downloadAsJson = () => {
    if (!reportData) return;
    const dataStr = JSON.stringify(reportData, null, 2);
    const blob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `report_${reportData.user_id}_${startDate}_${endDate}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!initialized) {
    return <div>Loading Keycloak...</div>;
  }

  if (!keycloak.authenticated) {
    return (
      <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100">
        <button
          onClick={() => keycloak.login()}
          className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
        >
          Login
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center min-h-screen bg-gray-100 p-4">
      <div className="p-8 bg-white rounded-lg shadow-md w-full max-w-4xl">
        <h1 className="text-2xl font-bold mb-6">Usage Reports</h1>

        <div className="mb-4 flex flex-wrap gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700">Start Date</label>
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700">End Date</label>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={fetchReport}
            disabled={loading}
            className="px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600 disabled:opacity-50"
          >
            {loading ? 'Generating...' : 'Generate Report'}
          </button>
          {reportData && (
            <button
              onClick={downloadAsJson}
              className="px-4 py-2 bg-green-500 text-white rounded hover:bg-green-600"
            >
              Download JSON
            </button>
          )}
        </div>

        {error && (
          <div className="mt-4 p-4 bg-red-100 text-red-700 rounded">{error}</div>
        )}

        {reportData && (
          <div className="mt-6">
            <h2 className="text-xl font-semibold mb-2">
              Report for user #{reportData.user_id}
            </h2>
            <p>
              Period: {reportData.period.start} to {reportData.period.end}
            </p>
            <div className="mt-4 p-4 bg-gray-50 rounded">
              <h3 className="font-medium mb-2">Summary</h3>
              <ul className="list-disc list-inside">
                <li>Total movements: {reportData.summary.total_movements}</li>
                <li>Average response time: {reportData.summary.avg_response_ms} ms</li>
                <li>Number of days: {reportData.summary.total_days}</li>
              </ul>
            </div>

            <h3 className="font-medium mt-6 mb-2">Daily Statistics</h3>
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200 border">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Date</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Movements</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Avg response (ms)</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Battery drain (%)</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Sessions</th>
                    <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Firmware</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200">
                  {reportData.daily_stats.map((day) => (
                    <tr key={day.report_date}>
                      <td className="px-4 py-2 text-sm">{day.report_date}</td>
                      <td className="px-4 py-2 text-sm">{day.total_movements}</td>
                      <td className="px-4 py-2 text-sm">{day.avg_response_ms}</td>
                      <td className="px-4 py-2 text-sm">{day.battery_drain_pct}</td>
                      <td className="px-4 py-2 text-sm">{day.session_count}</td>
                      <td className="px-4 py-2 text-sm">{day.firmware_version}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default ReportPage;