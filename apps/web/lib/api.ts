const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8080/api'

class APIClient {
  private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const token = localStorage.getItem('access_token')
    
    const response = await fetch(`${API_BASE_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': token ? `Bearer ${token}` : '',
        ...options?.headers,
      },
    })

    if (!response.ok) {
      throw new Error(`API Error: ${response.status}`)
    }

    return response.json()
  }

  // Streams
  async getTotalDailyStreams(days: string) {
    return this.request<{ labels: string[], values: number[] }>(
      `/streams/total-daily?days=${days}`
    )
  }

  async getStreamDates(days: string) {
    return this.request<{ dates: string[] }>(
      `/streams/dates?days=${days}`
    )
  }

  async getTopDeltas(date: string, limit: number = 100) {
    return this.request<{ rows: Array<{
      isrc: string
      title: string
      artist: string
      delta: number
    }> }>(
      `/streams/top-deltas?date=${date}&limit=${limit}`
    )
  }

  // Playlists
  async getPlaylists() {
    return this.request<Array<{
      playlist_id: string
      playlist_name: string
      followers: number
      delta: number
      date: string
      web_url: string
    }>>('/playlists/list')
  }

  async getPlaylistSeries(playlistId: string, days: string) {
    return this.request<{
      labels: string[]
      followers: number[]
      deltas: number[]
    }>(`/playlists/${encodeURIComponent(playlistId)}/series?days=${days}`)
  }

  async getTotalPlaylistSeries(playlistIds: string[], days: string) {
    return this.request<{
      labels: string[]
      follower_datasets: any[]
      delta_datasets: any[]
    }>('/playlists/total-series', {
      method: 'POST',
      body: JSON.stringify({ playlist_ids: playlistIds, days })
    })
  }

  // Catalogue
  async getCatalogueSizeSeries() {
    return this.request<{
      labels: string[]
      values: number[]
      count: number
      min_date: string
      max_date: string
    }>('/catalogue/size-series')
  }

  async getHealthStatusHeatmap() {
    return this.request<{
      xLabels: string[]
      yLabels: string[]
      data: Array<{ x: string, y: string, v: number }>
      catalogueTotalSize: number
    }>('/catalogue/health-status-heatmap')
  }

  async addTracks(tracks: Array<{ isrc: string, title?: string, artist?: string }>) {
    return this.request('/catalogue/tracks', {
      method: 'POST',
      body: JSON.stringify({ tracks })
    })
  }

  async getTracks() {
    return this.request<Array<{
      track_uid: string
      isrc: string
      title: string
      artist: string
    }>>('/catalogue/tracks')
  }

  // Artists
  async getTopArtistsShare(date?: string) {
    const params = date ? `?date=${date}` : ''
    return this.request<{
      date: string
      labels: string[]
      shares: number[]
    }>(`/artists/top-share${params}`)
  }

  // Auth
  async login(email: string, password: string) {
    return this.request<{
      user: any
      session: { access_token: string, refresh_token: string }
    }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password })
    })
  }

  async refresh(refreshToken: string) {
    return this.request<{ access_token: string }>('/auth/refresh', {
      method: 'POST',
      body: JSON.stringify({ refresh_token: refreshToken })
    })
  }
}

export const api = new APIClient()
