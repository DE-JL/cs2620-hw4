# Engineering Notebook: Replication Design Exercise

> [!NOTE]
> **Authors:** Daniel Li, Rajiv Swamy
>
> **Date:** 3/26/25

## 3/16

- Idea: use 3 servers
    - Primary-based write replication: coordinator will wait for all replicas to respond
    - Since there are only 3 servers, this should be manageable
- Need to address leader election first
- Garcia-Molina [**Bully Algorithm**](https://en.wikipedia.org/wiki/Bully_algorithm) for leader election
    - The algorithm assumes that all servers have unique IDs and know about each other's IDs
    - The goal is to elect the online server with the greatest ID as the leader
    - Followers use periodic heartbeats to determine when the leader has gone down
- **Pros:**
    - Relatively simple to implement
    - Seems quite robust with a relatively consistent convergence speed
    - Quite adaptable to adding more servers
- **Cons:**
    - Need mutexes to avoid race conditions
    - There are times when a server has no leader (waiting on a coordinator request)
    -

## 3/17

- Bully algorithm prototype seems to be working!
- The main goal today is to figure out how to cleanly integrate it with an existing service
- The problem is that the leader can crash in the middle of executing a request
    - For example, a server forwards a request to the leader (a send message request)
    - The leader is in the process of propagating this change to the other followers
    - However, the leader crashes midway
    - A new leader is elected but this leader must now replay those changes

What is _supposed_ to happen? Let's assume for a moment that there are no crashes.
One leader, two followers, all is working as normal.

- The leader gets some query.
- It executes the query and writes the query to its log. It _commits_ both of these changes atomically.
- It forwards the query to all followers and waits for a response/timeout.
- It then acknowledges the query back to the client.
- The commit log is essentially an entire history from which the state of the server can be rebuilt.

## 3/18

- Even with commit logs, there can be moments where the logs don't match up.
- Need to come up with a way to synchronize the commit logs, this is difficult!
- The key lies in how we elect a new leader.
- We should always elect the leader with the LATEST commit.
- To determine latest, we can just look at the index of the latest commit.

### Critical Points

- We need to guarantee that the following will never happen:
    - Server 1 and server 2 have a different commit $i$ for some $i$

## 3/19

- Full send?
