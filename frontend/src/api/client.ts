import axios, { InternalAxiosRequestConfig, AxiosResponse, AxiosError } from 'axios';

const client = axios.create({
  baseURL: '/api/v1',
});

export { client };

let accessToken: string | null = null;

export const setAccessToken = (token: string | null) => {
  accessToken = token;
};

client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken && config.headers) {
    config.headers.Authorization = `Bearer ${accessToken}`;
  }
  return config;
});

client.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    
    // If the error is 401 and we haven't retried yet
    if (error.response?.status === 401 && originalRequest && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshToken = localStorage.getItem('refresh_token');
      
      if (refreshToken) {
        try {
          // Use a fresh axios instance to avoid interceptor loops
          const res = await axios.post('/api/v1/auth/refresh', { 
            refresh_token: refreshToken 
          });
          
          const newAccessToken = res.data.access_token;
          const newRefreshToken = res.data.refresh_token;
          
          accessToken = newAccessToken;
          localStorage.setItem('refresh_token', newRefreshToken);
          
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${newAccessToken}`;
          }
          
          return client(originalRequest);
        } catch (refreshError: any) {
          console.error("Token refresh failed:", refreshError);
          localStorage.removeItem('refresh_token');
          // If refresh fails, we should clear everything and let the application 401/403 flow handle logout
          accessToken = null;
        }
      }
    }
    
    return Promise.reject(error);
  }
);

export default client;
