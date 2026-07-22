# Operation Instances

An operation instance applies a family and filesystem binding to concrete
analysis entries. It declares entry functions, phases, role selectors, return
contracts, effect metadata, summary IDs, legal exits, and discovery context.

It must not redefine family actions or binding callees. Entry names are
regression seeds and applicability anchors, not bug labels. Candidate status is
derived only after source facts are propagated through the composed runtime
protocol and checked at an exit.

Protocol D/E currently use operation instances. Protocol A-C remain supported
flat configurations because package schema v1 only composes a single effect
lifecycle per operation.
