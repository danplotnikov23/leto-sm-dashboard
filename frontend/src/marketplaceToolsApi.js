export const API_BASE =
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8010";

export async function runMarketplaceTool(path, formData) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body: formData,
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const detail =
      typeof payload?.detail === "string"
        ? payload.detail
        : "Не удалось обработать файлы";
    throw new Error(detail);
  }
  return payload;
}

export function artifactUrl(downloadUrl) {
  return `${API_BASE}${downloadUrl}`;
}
