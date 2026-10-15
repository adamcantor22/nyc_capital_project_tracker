from rail import chain, joined, network, shortest, until_corridor

# About 11 m per 0.0001 degree of latitude at the city's latitude.
A, B, C, D = (-73.9, 40.80), (-73.9, 40.81), (-73.9, 40.82), (-73.9, 40.83)


def test_network_joins_ends_within_the_snap_distance():
    near = (-73.9, 40.81015)  # about 17 m from B
    far = (-73.9, 40.8105)  # about 55 m from B
    adj = network([[A, B], [near, C], [far, D]])
    assert any(n == (round(near[0], 6), round(near[1], 6)) for n, _, i in adj[B] if i is None)
    assert not any(n == (round(far[0], 6), round(far[1], 6)) for n, _, _ in adj[B])


def test_shortest_path_follows_the_line_and_leaves_spurs_out():
    spur = (-73.95, 40.81)
    lines = [[A, B], [B, C], [B, spur], [C, D]]
    path = shortest(network(lines), A, D)
    assert [n for n, _ in path] == [A, B, C, D]
    assert chain(lines, path) == [[A, B], [B, C], [C, D]]


def test_chain_turns_lines_to_run_along_the_path():
    lines = [[B, A], [C, B]]
    assert chain(lines, shortest(network(lines), A, C)) == [[A, B], [B, C]]


def test_until_corridor_stops_at_the_first_point_on_the_corridor():
    corridor = [(-73.9, 40.82), (-73.95, 40.82)]
    kept, junction = until_corridor([[D, (-73.9, 40.825)], [(-73.9, 40.825), C, B]], corridor)
    assert kept == [[D, (-73.9, 40.825)], [(-73.9, 40.825), C]] and junction == C
    assert until_corridor([[A, B]], corridor) == ([[A, B]], None)


def test_joined_draws_ordered_lines_as_one_from_the_previous_part():
    near_b = (-73.9, 40.81015)  # a gap of about 17 m, within SNAP_M
    assert joined([[A, B], [near_b, C], [C, D]], start=(-73.9, 40.79)) == [(-73.9, 40.79), A, B, near_b, C, D]
