package storage

import (
	"context"
	"fmt"
	"time"

	"github.com/redis/go-redis/v9"
)

// RedisClient wraps the go-redis client.
type RedisClient struct {
	client *redis.Client
}

// NewRedisClient creates a new Redis client and verifies connection.
func NewRedisClient(addr string, password string, db int) (*RedisClient, error) {
	client := redis.NewClient(&redis.Options{
		Addr:     addr,
		Password: password,
		DB:       db,
	})

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	if err := client.Ping(ctx).Err(); err != nil {
		return nil, fmt.Errorf("failed to connect to redis: %w", err)
	}

	return &RedisClient{client: client}, nil
}

// PublishEvent sends an event to a Redis Stream using XADD.
// Phase 7: Uses MaxLen=5000 with Approx to cap memory usage.
func (r *RedisClient) PublishEvent(ctx context.Context, stream string, data map[string]interface{}) error {
	return r.client.XAdd(ctx, &redis.XAddArgs{
		Stream: stream,
		Values: data,
		MaxLen: 5000, // Cap stream size for memory optimization
		Approx: true, // Allow ~5000 for better performance
	}).Err()
}

// Close closes the Redis connection.
func (r *RedisClient) Close() error {
	return r.client.Close()
}
