import { MAX_BOT_STARTAPP_URL } from "./appHelpers";

export function LaunchGate() {
  return (
    <div className="screen-center">
      <div className="error-card launch-gate">
        <strong>Откройте ПриДел внутри MAX</strong>
        <p>
          Мини-приложение работает внутри клиента MAX. Если открыть ссылку в обычном браузере,
          рабочая сессия не создаётся.
        </p>
        <div className="action-row">
          <button className="btn btn-primary" onClick={() => window.location.assign(MAX_BOT_STARTAPP_URL)}>
            Открыть в MAX
          </button>
        </div>
        <p className="muted">
          Если MAX уже открыт, перейдите в бота ПриДел и нажмите «Открыть приложение».
        </p>
      </div>
    </div>
  );
}

