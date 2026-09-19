# Predictive (Plan-Based/Waterfall) Approach

## Overview
The predictive approach is a traditional project management methodology where scope, schedule, and cost are determined early and changes are carefully managed through formal change control.

## When to Use Predictive Approach
- Requirements are well-understood and stable
- Technology is well-established
- Regulatory/compliance environments requiring strict documentation
- Physical construction, manufacturing projects
- Low uncertainty and complexity

## Schedule Management

### Key Processes
1. **Plan Schedule Management**: Establish policies and procedures
2. **Define Activities**: Identify specific actions to produce deliverables
3. **Sequence Activities**: Identify and document relationships among activities
4. **Estimate Activity Durations**: Estimate time needed
5. **Develop Schedule**: Analyze sequences, durations, resources to create schedule
6. **Control Schedule**: Monitor status and manage changes

### Critical Path Method (CPM)
The critical path is the **longest path** through a project network diagram, determining the **shortest possible project duration**.

**Key Concepts:**
- **Float/Slack**: Amount of time an activity can be delayed without delaying the project (Critical path activities have ZERO float)
- **Forward Pass**: Calculates Early Start (ES) and Early Finish (EF)
- **Backward Pass**: Calculates Late Start (LS) and Late Finish (LF)
- **Free Float**: Time an activity can be delayed without delaying the next activity
- **Total Float**: Time an activity can be delayed without delaying the project end date

**Formula:**
- Float = LS - ES (or LF - EF)
- Critical Path activities: Float = 0

**Simple Example:**
If Activity A takes 5 days and Activity B (dependent on A) takes 3 days, and there's a parallel Activity C taking 4 days that also must finish before the final activity, the critical path is whichever path (A→B or C) takes longer in total.

### Network Diagram Types
- **Precedence Diagramming Method (PDM)**: Most common, uses nodes for activities
- **Dependency types**:
  - Finish-to-Start (FS): Most common - B can't start until A finishes
  - Start-to-Start (SS): B can't start until A starts
  - Finish-to-Finish (FF): B can't finish until A finishes
  - Start-to-Finish (SF): Rare - B can't finish until A starts

### Schedule Compression Techniques
1. **Crashing**: Adding resources to shorten duration (increases cost)
2. **Fast Tracking**: Performing activities in parallel that were originally sequential (increases risk)

## Cost Management

### Earned Value Management (EVM)
A methodology combining scope, schedule, and cost to assess project performance.

**Key Terms:**
- **PV (Planned Value)**: Budgeted cost of work scheduled
- **EV (Earned Value)**: Budgeted cost of work actually performed
- **AC (Actual Cost)**: Actual cost incurred for work performed
- **BAC (Budget at Completion)**: Total budget for the project

**Key Formulas:**
| Metric | Formula | Interpretation |
|--------|---------|-----------------|
| Cost Variance (CV) | EV - AC | Positive = under budget |
| Schedule Variance (SV) | EV - PV | Positive = ahead of schedule |
| Cost Performance Index (CPI) | EV / AC | >1 = under budget |
| Schedule Performance Index (SPI) | EV / PV | >1 = ahead of schedule |
| Estimate at Completion (EAC) | BAC / CPI | Projected total cost |
| Estimate to Complete (ETC) | EAC - AC | Remaining cost needed |
| Variance at Completion (VAC) | BAC - EAC | Projected variance at end |

**Real-World Example:**
If BAC = $100,000, EV = $40,000, AC = $50,000:
- CV = 40,000 - 50,000 = -$10,000 (over budget)
- CPI = 40,000/50,000 = 0.8 (getting $0.80 value per $1 spent — inefficient)

### Cost Estimating Techniques
- **Analogous Estimating**: Uses historical data from similar projects (top-down, less accurate, fast)
- **Parametric Estimating**: Uses statistical relationship between data (e.g., cost per square foot)
- **Bottom-Up Estimating**: Estimates individual work packages, sums up (most accurate, time-consuming)
- **Three-Point Estimating**: Uses optimistic, pessimistic, most likely estimates
  - PERT Formula: (Optimistic + 4×Most Likely + Pessimistic) / 6

## Risk Management

### Risk Management Processes
1. Plan Risk Management
2. Identify Risks
3. Perform Qualitative Risk Analysis
4. Perform Quantitative Risk Analysis
5. Plan Risk Responses
6. Implement Risk Responses
7. Monitor Risks

### Risk Response Strategies

**For Negative Risks (Threats):**
- **Avoid**: Eliminate the threat entirely
- **Mitigate**: Reduce probability/impact
- **Transfer**: Shift impact to third party (e.g., insurance)
- **Accept**: Acknowledge risk, no proactive action (active or passive)

**For Positive Risks (Opportunities):**
- **Exploit**: Ensure opportunity is realized
- **Enhance**: Increase probability/impact
- **Share**: Allocate ownership to third party
- **Accept**: Take advantage if it occurs, no proactive action

### Risk Register
A document containing:
- List of identified risks
- Risk owners
- Risk responses
- Probability and impact ratings

## Quality Management
- **Plan Quality**: Identify quality requirements/standards
- **Manage Quality (QA)**: Audit quality requirements, ensure appropriate standards/processes used
- **Control Quality (QC)**: Monitor and record results of executing quality activities

**Cost of Quality:**
- **Cost of Conformance**: Prevention costs + Appraisal costs
- **Cost of Nonconformance**: Internal failure costs + External failure costs

## Procurement Management

### Contract Types
| Contract Type | Risk to Seller | Risk to Buyer | When to Use |
|---------------|-----------------|----------------|-------------|
| Fixed Price (FP) | High | Low | Well-defined scope |
| Cost Reimbursable (CR) | Low | High | Uncertain scope |
| Time & Materials (T&M) | Medium | Medium | Staff augmentation |

## Integration Management
- **Develop Project Charter**: Authorize project
- **Develop Project Management Plan**: Define, prepare, coordinate all subsidiary plans
- **Direct and Manage Project Work**: Lead and perform work
- **Manage Project Knowledge**: Use existing knowledge, create new knowledge
- **Monitor and Control Project Work**: Track, review, report progress
- **Perform Integrated Change Control**: Review and approve changes
- **Close Project or Phase**: Finalize all activities

---

**Note**: Original study content. Real-world project management application for CAPM exam preparation.
