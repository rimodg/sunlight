"""
SUNLIGHT Stork-to-TCA Scale Pipeline
Campaign configuration for processing millions of contracts through TCA overnight.
Uses Stork's Campaign mode for multi-day, restart-safe execution.

Resolves UNDP Problem #5: 70M Contracts Too Many For Humans
"""

import json
import math
import time
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class BatchConfig:
    """Configuration for a TCA batch processing run."""
    batch_id: str
    country_code: str
    country_name: str
    total_contracts: int
    batch_size: int = 1000  # Contracts per Stork agent
    priority_threshold: float = 0.4  # TCA confidence below this = priority finding
    min_contract_value: float = 10000  # Skip contracts below this value
    currency: str = "USD"
    

@dataclass
class BatchResult:
    """Result from a single batch of TCA analysis."""
    batch_id: str
    batch_index: int
    contracts_processed: int
    contracts_skipped: int  # Below value threshold
    findings_priority_i: int  # TCA confidence < 0.3
    findings_priority_ii: int  # TCA confidence 0.3-0.5
    findings_elevated: int  # TCA confidence 0.5-0.6
    structurally_sound: int  # TCA confidence >= 0.6
    total_projected_recovery: float
    processing_time_seconds: float
    errors: int = 0


@dataclass
class CampaignState:
    """
    Persistent state for a Stork campaign.
    Survives restarts through disk persistence.
    """
    campaign_id: str
    country_code: str
    country_name: str
    status: str  # "planning", "running", "paused", "completed", "failed"
    
    # Progress
    total_contracts: int = 0
    contracts_processed: int = 0
    contracts_remaining: int = 0
    current_batch: int = 0
    total_batches: int = 0
    
    # Findings
    total_findings: int = 0
    priority_i_findings: int = 0
    priority_ii_findings: int = 0
    total_projected_recovery: float = 0.0
    
    # Timing
    started_at: str = ""
    estimated_completion: str = ""
    last_checkpoint: str = ""
    
    # Conviction (Stork memory — one per campaign)
    conviction: str = ""
    
    # Batch results
    batch_results: List[BatchResult] = field(default_factory=list)


class ScalePipeline:
    """
    Orchestrates large-scale TCA analysis across millions of contracts.
    Designed to run as a Stork Campaign with overnight mode.
    
    Architecture:
    1. PLAN phase: Count contracts, compute batch plan, estimate time
    2. DISPATCH phase: Spawn Many agents, each processing one batch
    3. COLLECT phase: Aggregate results, generate sitrep
    4. CERTIFY phase: Feed aggregated results to CertificationEngine
    
    Each phase is a campaign step that checkpoints to disk.
    """
    
    # Performance estimates (based on TCA engine benchmarks)
    CONTRACTS_PER_SECOND = 50  # TCA analysis throughput
    OVERHEAD_PER_BATCH = 5  # Seconds of setup per batch
    MAX_PARALLEL_AGENTS = 10  # Stork Spawn Many limit
    
    def __init__(self):
        self.campaigns: Dict[str, CampaignState] = {}
    
    def plan_campaign(
        self,
        country_code: str,
        country_name: str,
        total_contracts: int,
        batch_size: int = 1000,
        min_value: float = 10000
    ) -> CampaignState:
        """
        Phase 1: Plan the campaign.
        Computes batches, estimates time, creates persistent state.
        """
        campaign_id = f"tca-{country_code}-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}"
        
        # Estimate contracts above value threshold (typically 60-80% of total)
        estimated_eligible = int(total_contracts * 0.7)
        
        total_batches = math.ceil(estimated_eligible / batch_size)
        
        # Time estimate
        serial_time = estimated_eligible / self.CONTRACTS_PER_SECOND
        parallel_waves = math.ceil(total_batches / self.MAX_PARALLEL_AGENTS)
        parallel_time = (serial_time / self.MAX_PARALLEL_AGENTS) + (parallel_waves * self.OVERHEAD_PER_BATCH)
        
        estimated_completion = datetime.utcnow() + timedelta(seconds=parallel_time)
        
        state = CampaignState(
            campaign_id=campaign_id,
            country_code=country_code,
            country_name=country_name,
            status="planning",
            total_contracts=total_contracts,
            contracts_remaining=estimated_eligible,
            total_batches=total_batches,
            started_at=datetime.utcnow().isoformat() + "Z",
            estimated_completion=estimated_completion.isoformat() + "Z",
        )
        
        self.campaigns[campaign_id] = state
        return state
    
    def generate_batch_configs(self, campaign_id: str) -> List[BatchConfig]:
        """Generate batch configurations for Stork Spawn Many dispatch."""
        state = self.campaigns.get(campaign_id)
        if not state:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        configs = []
        for i in range(state.total_batches):
            configs.append(BatchConfig(
                batch_id=f"{campaign_id}-batch-{i:04d}",
                country_code=state.country_code,
                country_name=state.country_name,
                total_contracts=min(1000, state.contracts_remaining - (i * 1000)),
            ))
        
        return configs
    
    def generate_stork_campaign_spec(self, campaign_id: str) -> Dict:
        """
        Generate the actual Stork campaign specification.
        This is what Hugo's Stork system consumes.
        """
        state = self.campaigns.get(campaign_id)
        if not state:
            raise ValueError(f"Campaign {campaign_id} not found")
        
        batches = self.generate_batch_configs(campaign_id)
        
        # Split into waves of MAX_PARALLEL_AGENTS
        waves = []
        for i in range(0, len(batches), self.MAX_PARALLEL_AGENTS):
            wave_batches = batches[i:i + self.MAX_PARALLEL_AGENTS]
            waves.append({
                "wave_index": len(waves),
                "mode": "spawn_many",
                "agents": [
                    {
                        "task": f"Run TCA structural analysis on batch {b.batch_id}",
                        "config": {
                            "batch_id": b.batch_id,
                            "country": b.country_code,
                            "batch_size": b.total_contracts,
                            "priority_threshold": b.priority_threshold,
                            "min_value": b.min_contract_value,
                        },
                        "tools_required": ["tca_analyze_text", "vault_deposit"],
                        "deposit_to_kd": True,
                        "tags": ["sunlight", "tca-scale", state.country_code],
                    }
                    for b in wave_batches
                ]
            })
        
        return {
            "campaign_id": campaign_id,
            "name": f"SUNLIGHT TCA Scale — {state.country_name} ({state.total_contracts:,} contracts)",
            "type": "campaign",
            "steps": [
                {
                    "step": 1,
                    "name": "data_extraction",
                    "description": f"Extract {state.country_name} contracts from OCDS feed, filter by value >= $10K",
                    "mode": "spawn",
                    "checkpoint": True,
                },
                {
                    "step": 2,
                    "name": "tca_analysis",
                    "description": f"Run TCA on {state.total_batches} batches across {len(waves)} waves",
                    "mode": "chain",
                    "sub_steps": waves,
                    "checkpoint_per_wave": True,
                },
                {
                    "step": 3,
                    "name": "aggregation",
                    "description": "Aggregate batch results into country-level findings",
                    "mode": "spawn",
                    "checkpoint": True,
                },
                {
                    "step": 4,
                    "name": "certification",
                    "description": f"Generate Structural Health Certification for {state.country_name}",
                    "mode": "spawn",
                    "tools_required": ["certification_engine"],
                    "checkpoint": True,
                },
                {
                    "step": 5,
                    "name": "deposit",
                    "description": "Deposit all findings and certification to KD",
                    "mode": "spawn",
                    "tools_required": ["metabolize"],
                    "checkpoint": True,
                },
            ],
            "overnight_mode": True,
            "sitrep_on_completion": True,
            "conviction_template": f"Country {state.country_name}: [structural pattern discovered]",
            "estimated_duration_seconds": int(
                state.contracts_remaining / self.CONTRACTS_PER_SECOND / self.MAX_PARALLEL_AGENTS * 1.5  # 1.5x safety margin
            ),
            "disk_persistence_path": f"campaigns/{campaign_id}/state.json",
        }
    
    def process_batch_result(self, campaign_id: str, result: BatchResult):
        """Record a batch result and update campaign state."""
        state = self.campaigns.get(campaign_id)
        if not state:
            return
        
        state.batch_results.append(result)
        state.contracts_processed += result.contracts_processed
        state.contracts_remaining -= result.contracts_processed
        state.current_batch += 1
        state.total_findings += result.findings_priority_i + result.findings_priority_ii
        state.priority_i_findings += result.findings_priority_i
        state.priority_ii_findings += result.findings_priority_ii
        state.total_projected_recovery += result.total_projected_recovery
        state.last_checkpoint = datetime.utcnow().isoformat() + "Z"
        
        # Update status
        if state.contracts_remaining <= 0:
            state.status = "completed"
        else:
            state.status = "running"
    
    def generate_sitrep(self, campaign_id: str) -> str:
        """Generate morning sitrep for a campaign."""
        state = self.campaigns.get(campaign_id)
        if not state:
            return f"Campaign {campaign_id} not found"
        
        progress = state.contracts_processed / max(state.total_contracts, 1)
        
        lines = []
        lines.append("═" * 60)
        lines.append(f"SUNLIGHT TCA SCALE CAMPAIGN — SITREP")
        lines.append("═" * 60)
        lines.append(f"Campaign: {state.campaign_id}")
        lines.append(f"Country: {state.country_name} ({state.country_code})")
        lines.append(f"Status: {state.status.upper()}")
        lines.append(f"Progress: {progress:.1%} ({state.contracts_processed:,} / {state.total_contracts:,})")
        lines.append(f"Batches: {state.current_batch} / {state.total_batches}")
        lines.append("")
        
        lines.append("FINDINGS:")
        lines.append(f"  Priority I (critical):  {state.priority_i_findings}")
        lines.append(f"  Priority II (elevated): {state.priority_ii_findings}")
        lines.append(f"  Total findings:         {state.total_findings}")
        lines.append(f"  Projected recovery:     USD {state.total_projected_recovery:,.2f}")
        lines.append("")
        
        if state.batch_results:
            avg_time = sum(r.processing_time_seconds for r in state.batch_results) / len(state.batch_results)
            total_errors = sum(r.errors for r in state.batch_results)
            lines.append(f"PERFORMANCE:")
            lines.append(f"  Avg batch time:     {avg_time:.1f}s")
            lines.append(f"  Total errors:       {total_errors}")
            lines.append(f"  Throughput:         {state.contracts_processed / max(sum(r.processing_time_seconds for r in state.batch_results), 1):.0f} contracts/sec")
        
        lines.append("")
        lines.append(f"Started: {state.started_at}")
        lines.append(f"Est. completion: {state.estimated_completion}")
        lines.append(f"Last checkpoint: {state.last_checkpoint}")
        
        if state.conviction:
            lines.append(f"\nCONVICTION: {state.conviction}")
        
        lines.append("═" * 60)
        return "\n".join(lines)
    
    def estimate_global_run(self) -> Dict:
        """
        Estimate resources for running TCA on the full UNDP Compass dataset.
        70 million contracts across 60 countries.
        """
        total_contracts = 70_000_000
        eligible_contracts = int(total_contracts * 0.7)  # Above value threshold
        
        # Per-country estimates
        avg_contracts_per_country = eligible_contracts // 60
        batches_per_country = math.ceil(avg_contracts_per_country / 1000)
        waves_per_country = math.ceil(batches_per_country / self.MAX_PARALLEL_AGENTS)
        
        # Time per country
        time_per_country_seconds = avg_contracts_per_country / self.CONTRACTS_PER_SECOND / self.MAX_PARALLEL_AGENTS * 1.5
        time_per_country_hours = time_per_country_seconds / 3600
        
        # Total time (running countries sequentially, batches parallel within country)
        total_serial_hours = time_per_country_hours * 60
        
        # Running 5 countries in parallel via Stork campaigns
        countries_parallel = 5
        total_parallel_hours = total_serial_hours / countries_parallel
        total_parallel_days = total_parallel_hours / 24
        
        return {
            "total_contracts": total_contracts,
            "eligible_contracts": eligible_contracts,
            "countries": 60,
            "avg_contracts_per_country": avg_contracts_per_country,
            "batches_per_country": batches_per_country,
            "time_per_country_hours": round(time_per_country_hours, 1),
            "total_serial_hours": round(total_serial_hours, 1),
            "parallel_countries": countries_parallel,
            "total_parallel_hours": round(total_parallel_hours, 1),
            "total_parallel_days": round(total_parallel_days, 1),
            "estimated_findings": int(eligible_contracts * 0.05),  # ~5% finding rate
            "estimated_priority_i": int(eligible_contracts * 0.007),  # ~0.7% critical
        }


# ═══ DEMO ═══
if __name__ == "__main__":
    pipeline = ScalePipeline()
    
    # Plan a Senegal campaign
    state = pipeline.plan_campaign("SN", "Senegal", 12000)
    print(f"Campaign planned: {state.campaign_id}")
    print(f"Total batches: {state.total_batches}")
    print(f"Estimated completion: {state.estimated_completion}")
    
    # Generate Stork campaign spec
    spec = pipeline.generate_stork_campaign_spec(state.campaign_id)
    print(f"\nStork Campaign Spec:")
    print(json.dumps(spec, indent=2, default=str))
    
    # Simulate batch result
    pipeline.process_batch_result(state.campaign_id, BatchResult(
        batch_id=f"{state.campaign_id}-batch-0000",
        batch_index=0,
        contracts_processed=1000,
        contracts_skipped=142,
        findings_priority_i=7,
        findings_priority_ii=23,
        findings_elevated=45,
        structurally_sound=783,
        total_projected_recovery=2_850_000,
        processing_time_seconds=18.4,
    ))
    
    print(f"\n{pipeline.generate_sitrep(state.campaign_id)}")
    
    # Global estimate
    print("\n\nGLOBAL RUN ESTIMATE (70M contracts, 60 countries):")
    estimate = pipeline.estimate_global_run()
    for k, v in estimate.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
