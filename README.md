# AI Workflow Assessment

## Overview
This assessment provides a Python script, `generate_data.py`, that generates synthetic 3D point data in CSV format.

Each point includes:
- a 3D position
- a score value
- orientation data represented by roll, pitch, and yaw

The candidate is required to design and implement a visualizer that enables effective inspection and navigation of this data.

## Objective
The objective of this assessment is to build a tool that allows a user to explore the generated point data and inspect per-point score and angle information.

This assessment is intentionally open-ended.  
There is no single prescribed user interface, layout, or interaction model.

The evaluation is intended to measure not only implementation ability, but also the candidate's ability to interpret an ambiguous problem, structure a solution, and use AI effectively as part of the development workflow.
Stronger submissions will usually show a visible attempt to improve the usability and clarity of the first working version, rather than stopping at a merely functional result.

## Provided Material
- `generate_data.py`

No prebuilt dataset is provided.  
The candidate is expected to generate a CSV file locally and use it as the input to the visualizer.

## Assignment
The candidate shall:
1. Run `generate_data.py` to create a CSV file.
2. Inspect the generated data and understand its structure.
3. Design and implement a visualizer for the generated data.
4. Ensure that the resulting tool allows a user to navigate the point set and inspect per-point score and orientation information.

## Minimum Expectations
The submitted solution should:
- visualize the generated point data in a meaningful and usable manner
- provide a way to navigate or explore the data
- provide a way to inspect the score and orientation information for individual points
- run locally with clear execution instructions

## Intentionally Unspecified Areas
The following decisions are intentionally left to the candidate:
- choice of language, framework, or UI stack
- desktop app vs. web app vs. other local interface
- layout, controls, filtering, grouping, highlighting, and interaction design
- scope of additional supporting functionality

AI tools may be used freely during the assessment.

## Suggested Starting Point
Generate a CSV file:

```bash
python3 generate_data.py
```

This command creates `synthetic_points.csv` by default.

An alternative output path may also be specified:

```bash
python3 generate_data.py --output my_points.csv
```

## Deliverables
Please submit:
- your source code
- instructions for running your solution locally
- a short explanation of your design choices
- a brief note describing how you used AI during the task

Your report should also include at least one design iteration record containing:
- an intermediate screenshot of the visualizer
- a short explanation of what you believed needed improvement, and why
- the prompt or prompts you used to address that issue
- an updated screenshot after the change
- a short note describing what improved after the iteration

This is intended to show that you reviewed your own work critically and made a deliberate effort to improve it, rather than only producing a first-pass result.

## Evaluation Criteria
The submission will be evaluated based on:
- clarity of problem understanding and framing
- quality and usefulness of the visualization and interaction design
- practical usability, including whether the tool appears suitable for real review use
- completeness, reliability, and local runnability
- quality of design judgment and explanation of key decisions
- visible evidence of refinement and improvement beyond the initial working version
- clarity and meaningfulness of the reported AI usage

In particular, reviewers will consider questions such as:
- Did the candidate understand the generated data and the actual inspection problem?
- Is the visualization easy to read and navigate?
- Is it easy to inspect individual points and understand the important information?
- Does the solution feel practically usable rather than only technically functional?
- Does the implementation run clearly and cover the core task end to end?
- Is there evidence that the candidate tried to make the tool genuinely better, not merely complete?
- Does the submission show thoughtful use of AI rather than unexamined output?

## Notes
- There is no hidden required panel layout.
- There is no single correct interface.
- Strong submissions typically demonstrate sound product judgment, interaction design, and visible effort to refine the solution beyond basic functionality.
