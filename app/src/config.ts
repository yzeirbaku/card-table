const SERVER_URL = process.env.EXPO_PUBLIC_SERVER_URL ?? 'http://localhost:8000';

export const httpUrl = (path: string) => `${SERVER_URL}${path}`;
export const wsUrl = (path: string) => `${SERVER_URL.replace(/^http/, 'ws')}${path}`;
