# Delivery guarantees in stream processing

A stream processor reads events from a log, transforms them and writes results somewhere else. Because machines fail and networks drop messages, every stream system has to decide what it promises about how many times an event affects the result. There are three common guarantees.

## At-most-once, at-least-once and exactly-once

With at-most-once delivery a consumer records its position before it processes an event. If it crashes after recording the position but before finishing the work, the event is lost, because the restarted consumer resumes after it. This is the fastest option and is acceptable only when losing a few events does not matter, for example when sampling metrics.

With at-least-once delivery a consumer processes an event first and records its position afterwards. If it crashes between the two steps, it restarts from the last recorded position and processes the event a second time. Nothing is lost, but duplicates are possible, so the processing step should be idempotent: applying the same event twice must give the same result as applying it once.

Exactly-once processing means the effect of each event appears in the result once, even when failures cause retries. It is usually built from at-least-once delivery plus idempotent writes or transactions that commit the output and the consumer position together. Exactly-once is a property of the whole pipeline, not of the message transport alone.

## Offsets and consumer groups

Each record in a partition has an offset, a sequential number that identifies its position in that partition. A consumer group is a set of consumers that share the work of reading a topic: each partition is assigned to exactly one consumer in the group at a time, so adding consumers up to the number of partitions increases throughput. The group stores the last committed offset for every partition, and after a failure or a rebalance a consumer continues from that committed offset.

## Windows and late events

Stream processors often aggregate events over windows. A tumbling window has a fixed size and does not overlap with the next one. A sliding window advances in smaller steps than its size, so one event can belong to several windows. Events do not always arrive in the order they happened, so processors use event time and a watermark, which is the processor's estimate that no earlier events are still to come. An event that arrives after the watermark has passed its window is a late event and must be handled by an explicit rule, such as dropping it, sending it to a side output, or updating the earlier result.

## Backpressure

When a downstream step is slower than the source, the buffers between steps fill up. Backpressure is the mechanism that slows the producers down instead of letting the system run out of memory. A pipeline without backpressure either drops data or crashes under a sudden burst of traffic.
