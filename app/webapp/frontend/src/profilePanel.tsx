import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "./api";
import { SectionCard, errorMessage } from "./appHelpers";

export function ProfilePanel({
  externalUserId,
  canPublishMasterProfile,
}: {
  externalUserId: number;
  canPublishMasterProfile: boolean;
}) {
  const queryClient = useQueryClient();
  const profileQuery = useQuery({
    queryKey: ["profile", externalUserId],
    queryFn: () => api.getProfile(externalUserId),
  });

  const publicProfileQuery = useQuery({
    queryKey: ["public-profile", externalUserId],
    queryFn: () => api.getPublicProfile(externalUserId),
    enabled: canPublishMasterProfile,
  });

  const [basicForm, setBasicForm] = useState({
    full_name: "",
    phone: "",
    specialization: "",
  });

  const [publicForm, setPublicForm] = useState({
    headline: "",
    city: "",
    bio: "",
    availability_status: "open",
    skills: "",
    is_public: false,
    accent_color: "#95c7ff",
  });

  useEffect(() => {
    if (!profileQuery.data) {
      return;
    }
    setBasicForm({
      full_name: profileQuery.data.full_name || "",
      phone: profileQuery.data.phone || "",
      specialization: profileQuery.data.specialization || "",
    });
  }, [profileQuery.data]);

  useEffect(() => {
    const data = publicProfileQuery.data;
    if (!data) {
      return;
    }
    setPublicForm({
      headline: data.edit.headline || "",
      city: data.edit.city || "",
      bio: data.edit.bio || "",
      availability_status: data.edit.availability_status || "open",
      skills: data.edit.skills.join(", "),
      is_public: data.edit.is_public,
      accent_color: data.edit.accent_color || "#95c7ff",
    });
  }, [publicProfileQuery.data]);

  const saveBasicMutation = useMutation({
    mutationFn: () => api.updateProfile(externalUserId, basicForm),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  const savePublicMutation = useMutation({
    mutationFn: () =>
      api.updatePublicProfile(externalUserId, {
        headline: publicForm.headline,
        city: publicForm.city,
        bio: publicForm.bio,
        availability_status: publicForm.availability_status,
        skills: publicForm.skills
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean),
        is_public: publicForm.is_public,
        accent_color: publicForm.accent_color,
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["public-profile", externalUserId] });
      await queryClient.invalidateQueries({ queryKey: ["masters"] });
      await queryClient.invalidateQueries({ queryKey: ["bootstrap", externalUserId] });
    },
  });

  return (
    <div className="panel-stack" data-testid="profile-panel">
      <SectionCard title="Аккаунт" subtitle="Только то, что нужно продукту для работы и доверия.">
        <div className="stack-form">
          <input
            className="input"
            placeholder="Как вас отображать"
            value={basicForm.full_name}
            onChange={(event) => setBasicForm((state) => ({ ...state, full_name: event.target.value }))}
          />
          <div className="row-grid">
            <input
              className="input"
              placeholder="Телефон"
              value={basicForm.phone}
              onChange={(event) => setBasicForm((state) => ({ ...state, phone: event.target.value }))}
            />
            <input
              className="input"
              placeholder="Специализация"
              value={basicForm.specialization}
              onChange={(event) => setBasicForm((state) => ({ ...state, specialization: event.target.value }))}
            />
          </div>
          <div className="action-row">
            <button className="btn btn-primary" onClick={() => void saveBasicMutation.mutateAsync()}>
              Сохранить аккаунт
            </button>
          </div>
        </div>
      </SectionCard>

      {canPublishMasterProfile ? (
        <>
          <SectionCard title="Публичная страница мастера" subtitle="Ваша витрина в сети мастеров и на рынке работ.">
            <div className="stack-form">
              <input
                className="input"
                placeholder="Короткий заголовок"
                value={publicForm.headline}
                onChange={(event) => setPublicForm((state) => ({ ...state, headline: event.target.value }))}
              />
              <div className="row-grid">
                <input
                  className="input"
                  placeholder="Город"
                  value={publicForm.city}
                  onChange={(event) => setPublicForm((state) => ({ ...state, city: event.target.value }))}
                />
                <select
                  className="input"
                  value={publicForm.availability_status}
                  onChange={(event) =>
                    setPublicForm((state) => ({ ...state, availability_status: event.target.value }))
                  }
                >
                  <option value="open">Свободен</option>
                  <option value="busy">Занят</option>
                  <option value="offline">Скрыт</option>
                </select>
              </div>
              <textarea
                className="textarea"
                placeholder="2–3 предложения о вашем стиле работы"
                value={publicForm.bio}
                onChange={(event) => setPublicForm((state) => ({ ...state, bio: event.target.value }))}
              />
              <input
                className="input"
                placeholder="Навыки через запятую"
                value={publicForm.skills}
                onChange={(event) => setPublicForm((state) => ({ ...state, skills: event.target.value }))}
              />
              <div className="row-grid">
                <label className="toggle">
                  <input
                    type="checkbox"
                    checked={publicForm.is_public}
                    onChange={(event) => setPublicForm((state) => ({ ...state, is_public: event.target.checked }))}
                  />
                  <span>Показывать страницу в сети</span>
                </label>
                <input
                  className="input"
                  placeholder="#95c7ff"
                  value={publicForm.accent_color}
                  onChange={(event) => setPublicForm((state) => ({ ...state, accent_color: event.target.value }))}
                />
              </div>
              <div className="action-row">
                <button className="btn btn-primary" onClick={() => void savePublicMutation.mutateAsync()}>
                  Обновить страницу
                </button>
              </div>
              {savePublicMutation.error ? (
                <p className="inline-error">{errorMessage(savePublicMutation.error, "Не удалось обновить публичную страницу")}</p>
              ) : null}
            </div>
          </SectionCard>

          <SectionCard title="Как видят вас люди" subtitle="Спокойный превью-блок без отдельного режима просмотра.">
            <article className="glass-card master-card market-card">
              <div className="master-accent" style={{ background: publicForm.accent_color || "#95c7ff" }} />
              <div className="card-topline">
                <span className={`pill ${publicForm.availability_status === "open" ? "tone-success" : publicForm.availability_status === "busy" ? "tone-warn" : "tone-muted"}`}>
                  {publicForm.availability_status === "open" ? "Свободен" : publicForm.availability_status === "busy" ? "Занят" : "Скрыт"}
                </span>
                <span className="muted">{publicForm.is_public ? "Страница видна" : "Страница скрыта"}</span>
              </div>
              <h4>{basicForm.full_name || profileQuery.data?.full_name || "Ваше имя"}</h4>
              <p className="card-title">{publicForm.headline || basicForm.specialization || "Мастер"}</p>
              <p>{publicForm.bio || "Добавьте короткое описание, чтобы людям было проще понять ваш стиль работы."}</p>
              <div className="meta-cloud">
                {publicForm.city ? <span>{publicForm.city}</span> : null}
                {basicForm.specialization ? <span>{basicForm.specialization}</span> : null}
              </div>
              <div className="tag-row">
                {publicForm.skills
                  .split(",")
                  .map((item) => item.trim())
                  .filter(Boolean)
                  .slice(0, 4)
                  .map((skill) => (
                    <span key={skill} className="tag">
                      {skill}
                    </span>
                  ))}
              </div>
            </article>
          </SectionCard>
        </>
      ) : null}
    </div>
  );
}
