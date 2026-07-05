// apiFetch.js
export async function apiFetch(endpoint, options = {}) {
  const token = localStorage.getItem("jwt_token");

  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {})
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(endpoint, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(`API 錯誤: ${response.status} ${response.statusText}`);
  }

  try {
    return await response.json();
  } catch {
    return await response.text();
  }
}
