package main

import (
    "context"
    "encoding/json"
    "log"
    "net/http"
    "os"
    "time"

    "github.com/gorilla/mux"
    "github.com/jackc/pgx/v5/pgxpool"
    "github.com/rs/cors"
    "github.com/joho/godotenv"
)

var db *pgxpool.Pool

type Config struct {
    DatabaseURL string
    Port        string
    JWTSecret   string
}

func loadConfig() *Config {
    godotenv.Load()
    
    return &Config{
        DatabaseURL: os.Getenv("DATABASE_URL"),
        Port:        getEnvOrDefault("PORT", "8080"),
        JWTSecret:   os.Getenv("JWT_SECRET"),
    }
}

func getEnvOrDefault(key, defaultValue string) string {
    if value := os.Getenv(key); value != "" {
        return value
    }
    return defaultValue
}

func main() {
    cfg := loadConfig()
    
    // Initialize database connection
    var err error
    db, err = pgxpool.New(context.Background(), cfg.DatabaseURL)
    if err != nil {
        log.Fatal("Failed to connect to database:", err)
    }
    defer db.Close()
    
    // Verify connection
    if err := db.Ping(context.Background()); err != nil {
        log.Fatal("Database ping failed:", err)
    }
    
    log.Println("Connected to TimescaleDB")
    
    // Setup routes
    r := mux.NewRouter()
    
    // API routes
    api := r.PathPrefix("/api").Subrouter()
    
    // Public endpoints
    api.HandleFunc("/health", healthHandler).Methods("GET")
    
    // Auth endpoints
    api.HandleFunc("/auth/login", loginHandler).Methods("POST")
    api.HandleFunc("/auth/refresh", refreshHandler).Methods("POST")
    
    // Protected endpoints (require JWT middleware)
    protected := api.PathPrefix("").Subrouter()
    protected.Use(authMiddleware)
    
    // Streams endpoints
    protected.HandleFunc("/streams/total-daily", getTotalDailyStreams).Methods("GET")
    protected.HandleFunc("/streams/top-deltas", getTopDeltas).Methods("GET")
    protected.HandleFunc("/streams/dates", getStreamDates).Methods("GET")
    
    // Playlists endpoints
    protected.HandleFunc("/playlists/list", getPlaylistsList).Methods("GET")
    protected.HandleFunc("/playlists/{id}/series", getPlaylistSeries).Methods("GET")
    protected.HandleFunc("/playlists/total-series", getTotalPlaylistSeries).Methods("POST")
    
    // Catalogue endpoints
    protected.HandleFunc("/catalogue/size-series", getCatalogueSizeSeries).Methods("GET")
    protected.HandleFunc("/catalogue/health-status-heatmap", getHealthStatusHeatmap).Methods("GET")
    protected.HandleFunc("/catalogue/tracks", manageTracks).Methods("GET", "POST", "PUT", "DELETE")
    
    // Artists endpoints
    protected.HandleFunc("/artists/top-share", getTopArtistsShare).Methods("GET")
    
    // CORS
    c := cors.New(cors.Options{
        AllowedOrigins: []string{"http://localhost:3000", "https://isrcanalytics.com"},
        AllowedMethods: []string{"GET", "POST", "PUT", "DELETE", "OPTIONS"},
        AllowedHeaders: []string{"*"},
        AllowCredentials: true,
    })
    
    handler := c.Handler(r)
    
    log.Printf("Server starting on port %s", cfg.Port)
    if err := http.ListenAndServe(":"+cfg.Port, handler); err != nil {
        log.Fatal("Server failed to start:", err)
    }
}

func healthHandler(w http.ResponseWriter, r *http.Request) {
    response := map[string]interface{}{
        "status": "healthy",
        "timestamp": time.Now().Unix(),
        "database": db.Ping(context.Background()) == nil,
    }
    
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}

func authMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        token := r.Header.Get("Authorization")
        if token == "" {
            http.Error(w, "Unauthorized", http.StatusUnauthorized)
            return
        }
        
        // Validate JWT token (implementation depends on Supabase setup)
        // For now, pass through
        next.ServeHTTP(w, r)
    })
}

// Placeholder handlers - implementations in separate files
func loginHandler(w http.ResponseWriter, r *http.Request) {
    // Implement Supabase auth
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func refreshHandler(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getTotalDailyStreams(w http.ResponseWriter, r *http.Request) {
    userID := getUserIDFromContext(r)
    days := r.URL.Query().Get("days")
    if days == "" {
        days = "90"
    }
    
    query := `
        SELECT stream_date AS d, SUM(daily_delta)::bigint AS v
        FROM streams_daily_delta
        WHERE user_id = $1 
        AND stream_date >= CURRENT_DATE - CAST($2 AS INTEGER) * INTERVAL '1 day'
        GROUP BY stream_date 
        ORDER BY stream_date
    `
    
    rows, err := db.Query(context.Background(), query, userID, days)
    if err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    defer rows.Close()
    
    labels := []string{}
    values := []int64{}
    
    for rows.Next() {
        var date time.Time
        var value int64
        if err := rows.Scan(&date, &value); err != nil {
            continue
        }
        labels = append(labels, date.Format("2006-01-02"))
        values = append(values, value)
    }
    
    json.NewEncoder(w).Encode(map[string]interface{}{
        "labels": labels,
        "values": values,
    })
}

func getTopDeltas(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getStreamDates(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getPlaylistsList(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getPlaylistSeries(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getTotalPlaylistSeries(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getCatalogueSizeSeries(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getHealthStatusHeatmap(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func manageTracks(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getTopArtistsShare(w http.ResponseWriter, r *http.Request) {
    json.NewEncoder(w).Encode(map[string]string{"status": "not_implemented"})
}

func getUserIDFromContext(r *http.Request) string {
    // Extract user ID from JWT claims
    // For now return a placeholder
    return "00000000-0000-0000-0000-000000000000"
}
