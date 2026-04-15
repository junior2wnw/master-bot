import { useEffect } from "react";
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query";

import { api, ApiError } from "./api";
import { prepareBridge, resolveBridge } from "./bridge";
import { LaunchGate } from "./launchGate";
import { Shell } from "./Shell";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

function AppBody() {
  const bridge = resolveBridge();
  const shouldShowLaunchGate = !bridge.embedded && !bridge.initData && !api.hasActiveSession();

  useEffect(() => {
    prepareBridge();
  }, []);

  const authQuery = useQuery({
    queryKey: ["auth"],
    queryFn: () => api.auth(),
    enabled: !shouldShowLaunchGate,
  });

  const bootstrapQuery = useQuery({
    queryKey: ["bootstrap", authQuery.data?.telegram_id],
    queryFn: () => api.bootstrap(authQuery.data?.telegram_id as number),
    enabled: !shouldShowLaunchGate && Boolean(authQuery.data?.telegram_id),
  });

  if (shouldShowLaunchGate) {
    return <LaunchGate />;
  }

  if (authQuery.isPending || bootstrapQuery.isPending) {
    return (
      <div className="screen-center">
        <div className="loader-orb" />
        <p>Собираем новый ПриДел…</p>
      </div>
    );
  }

  if (authQuery.error || bootstrapQuery.error || !authQuery.data || !bootstrapQuery.data) {
    const error = (authQuery.error || bootstrapQuery.error) as ApiError | undefined;
    return (
      <div className="screen-center">
        <div className="error-card">
          <strong>Не удалось открыть Mini App</strong>
          <p>{error?.message || "Проверьте доступ и повторите запуск из MAX."}</p>
        </div>
      </div>
    );
  }

  return <Shell auth={authQuery.data} bootstrap={bootstrapQuery.data} />;
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppBody />
    </QueryClientProvider>
  );
}
