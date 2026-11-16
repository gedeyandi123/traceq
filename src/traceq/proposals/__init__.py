"""Proposals: importing a run as Proposals with an identity that holds across runs, and the
Proposal Decisions on them (spec #105).

``keys`` gives each Proposal its subject key and content hash; ``store`` imports a run folder
in one transaction; ``decisions`` records Proposal Decisions, says where each Proposal of a run
stands and counts them; ``api`` holds the database routes.
"""
