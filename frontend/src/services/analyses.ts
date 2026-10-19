import { API_BASE_URL } from '../config';
import type { AnalysisListResponse, AnalysisStatistics } from '../types';
import { fetchJson } from './api';

export async function getAnalyses(
  limit = 5,
  offset = 0,
  init?: RequestInit,
): Promise<AnalysisListResponse> {
  const url = `${API_BASE_URL}/api/analyses?limit=${limit}&offset=${offset}`;
  return fetchJson<AnalysisListResponse>(url, init);
}

export async function getStatistics(init?: RequestInit): Promise<AnalysisStatistics> {
  const url = `${API_BASE_URL}/api/statistics`;
  return fetchJson<AnalysisStatistics>(url, init);
}
