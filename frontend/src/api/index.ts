import axios from 'axios'

const http = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

// Response interceptor — extract data
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('API Error:', err)
    return Promise.reject(err)
  }
)

// Market APIs
export const marketApi = {
  getStocks: () => http.get('/v1/market/stocks'),
  getStockDaily: (code: string, params?: Record<string, any>) =>
    http.get(`/v1/market/stock/${code}`, { params }),
  getIndexes: () => http.get('/v1/market/indexes'),
  getIndexDaily: (code: string, params?: Record<string, any>) =>
    http.get(`/v1/market/index/${code}`, { params }),
}

// Strategy APIs
export const strategyApi = {
  getStrategies: () => http.get('/v1/strategy/'),
}

// Portfolio APIs
export const portfolioApi = {
  getPortfolio: () => http.get('/v1/portfolio/'),
}

// Analysis APIs
export const analysisApi = {
  getCorrelation: (params: Record<string, any>) =>
    http.get('/v1/analysis/correlation', { params }),
  getDrawdown: (params: Record<string, any>) =>
    http.get('/v1/analysis/drawdown', { params }),
  getSharpe: (params: Record<string, any>) =>
    http.get('/v1/analysis/sharpe', { params }),
  getDistribution: (params: Record<string, any>) =>
    http.get('/v1/analysis/returns-distribution', { params }),
}

// Finance APIs
export const financeApi = {
  getBalanceSheet: (params: Record<string, any>) =>
    http.get('/v1/finance/statements/balance', { params }),
  getIncomeStatement: (params: Record<string, any>) =>
    http.get('/v1/finance/statements/income', { params }),
  getCashFlow: (params: Record<string, any>) =>
    http.get('/v1/finance/statements/cashflow', { params }),
  getIndicators: (code: string, periods?: number) =>
    http.get(`/v1/finance/indicators/${code}`, { params: periods ? { periods } : {} }),
  getForecast: (code: string) =>
    http.get(`/v1/finance/forecast/${code}`),
}

// Factors APIs
export const factorsApi = {
  listFactors: (category?: string) =>
    http.get('/v1/factors/factors', { params: category ? { category } : {} }),
  getLatestDate: () => http.get('/v1/factors/factors/latest-date'),
  computeValues: (factorId: string, date?: string) =>
    http.get(`/v1/factors/factors/${factorId}/values`, { params: date ? { date } : {} }),
}

export default http
