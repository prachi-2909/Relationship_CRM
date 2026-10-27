package com.eko.rcrm.dc.ui.common

import androidx.compose.animation.animateContentSize
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.eko.rcrm.dc.domain.model.Commitment
import com.eko.rcrm.dc.domain.model.PerformanceReview
import com.eko.rcrm.dc.domain.model.Suggestion
import com.eko.rcrm.dc.ui.theme.MutedForeground

// Building blocks shared by the CSP pre-call screen and the SBI-official briefing, so both read and
// behave the same way as the web CRM.

/** What a person can do with the commitments and suggestions in a briefing. */
class BriefingActions(
    val busy: Boolean,
    /** Accept an AI suggestion ("open"), dismiss it ("cancelled"), or close a live one. */
    val onStatus: (id: Int, status: String, outcome: String?) -> Unit,
    /** "merge" or "separate" on a flagged near-duplicate. */
    val onDuplicate: (id: Int, decision: String) -> Unit,
    val onRate: (Suggestion, verdict: String) -> Unit
)

@Composable
fun SectionCard(
    title: String,
    subtitle: String? = null,
    accent: Color? = null,
    content: @Composable ColumnScope.() -> Unit
) {
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(
                text = title.uppercase(),
                style = MaterialTheme.typography.labelSmall,
                fontWeight = FontWeight.SemiBold,
                color = accent ?: MutedForeground
            )
            subtitle?.let {
                Text(
                    text = it,
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                    modifier = Modifier.padding(top = 2.dp)
                )
            }
            Spacer(modifier = Modifier.height(8.dp))
            content()
        }
    }
}

@Composable
fun BulletLine(bullet: String, text: String) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
        Text(text = bullet, style = MaterialTheme.typography.bodyMedium, color = MutedForeground)
        Text(
            text = text,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.padding(start = 8.dp)
        )
    }
}

/** A talking point / suggested follow-up with an explicit, optional "was it useful" rating. Nothing is
 * recorded unless the person taps - viewing a suggestion is not feedback. */
@Composable
fun SuggestionLine(s: Suggestion, actions: BriefingActions) {
    val good = if (s.isFollowup) "relevant" else "useful"
    val bad = if (s.isFollowup) "not_relevant" else "not_useful"
    val goodLabel = if (s.isFollowup) "Relevant" else "Useful"
    val badLabel = if (s.isFollowup) "Not relevant" else "Not useful"
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        BulletLine("→", s.text)
        Row(
            modifier = Modifier.fillMaxWidth().padding(start = 16.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (s.myVerdict == null) {
                TextButton(onClick = { actions.onRate(s, good) }, enabled = !actions.busy) { Text(goodLabel) }
                TextButton(onClick = { actions.onRate(s, bad) }, enabled = !actions.busy) { Text(badLabel) }
            } else {
                Text(
                    text = "You said: " + when (s.myVerdict) {
                        "useful" -> "useful"
                        "relevant" -> "relevant"
                        "not_useful" -> "not useful"
                        else -> "not relevant"
                    },
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
            }
        }
    }
}

@Composable
private fun CommitmentHeader(c: Commitment, youLabel: String, themLabel: String) {
    Text(text = c.text, style = MaterialTheme.typography.bodyMedium)
    Row(verticalAlignment = Alignment.CenterVertically) {
        StatusBadge(
            text = when (c.party) {
                "ours" -> youLabel
                "theirs" -> themLabel
                else -> "Both"
            },
            tone = Tone.Neutral
        )
        c.dueDate?.let {
            Text(text = "  by $it", style = MaterialTheme.typography.bodySmall, color = MutedForeground)
        }
        if (c.alsoMentioned > 0) {
            Text(
                text = "  · mentioned ${c.alsoMentioned + 1} times",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
        }
    }
}

/** An AI-suggested commitment awaiting a human decision, with the earlier look-alike beside it when the
 * system thinks it may be a repeat. Merging closes this one into the earlier one; nothing is deleted. */
@Composable
fun SuggestedCommitmentRow(c: Commitment, actions: BriefingActions, youLabel: String, themLabel: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        CommitmentHeader(c, youLabel, themLabel)
        c.possibleDuplicate?.let { dup ->
            Column(modifier = Modifier.fillMaxWidth().padding(top = 4.dp)) {
                Text(
                    text = "Looks like an earlier commitment (${dup.status}" +
                        (dup.dueDate?.let { ", by $it" } ?: "") + "):",
                    style = MaterialTheme.typography.labelSmall,
                    color = MutedForeground
                )
                Text(
                    text = dup.text,
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground,
                    modifier = Modifier.padding(start = 8.dp)
                )
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = { actions.onDuplicate(c.id, "merge") }, enabled = !actions.busy) {
                    Text("Same - merge")
                }
                TextButton(onClick = { actions.onDuplicate(c.id, "separate") }, enabled = !actions.busy) {
                    Text("Different - keep both")
                }
            }
        }
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { actions.onStatus(c.id, "open", null) }, enabled = !actions.busy) { Text("Accept") }
            TextButton(onClick = { actions.onStatus(c.id, "cancelled", null) }, enabled = !actions.busy) {
                Text("Dismiss")
            }
        }
    }
}

/** A live commitment. "Done" records that it was really fulfilled; "Not done" closes it as unfulfilled. */
@Composable
fun OpenCommitmentRow(c: Commitment, actions: BriefingActions, youLabel: String, themLabel: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        CommitmentHeader(c, youLabel, themLabel)
        Row(verticalAlignment = Alignment.CenterVertically) {
            TextButton(onClick = { actions.onStatus(c.id, "done", "fulfilled") }, enabled = !actions.busy) {
                Text("Mark done")
            }
            TextButton(onClick = { actions.onStatus(c.id, "cancelled", "not_fulfilled") }, enabled = !actions.busy) {
                Text("Not done")
            }
        }
    }
}

/** What the RM told the CSP last time (the RM states the performance; the CSP does not report it). */
@Composable
fun PerformanceCard(p: PerformanceReview) {
    SectionCard(
        title = "What you told them · ${p.fromIso.take(10)}",
        subtitle = "From your last call brief."
    ) {
        if (p.what.isNotEmpty()) {
            Text("Where they stand", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            p.what.forEach { BulletLine("•", it) }
        }
        if (p.why.isNotEmpty()) {
            Spacer(modifier = Modifier.height(6.dp))
            Text("Why", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            p.why.forEach { BulletLine("•", it) }
        }
        if (p.shouldBe.isNotEmpty()) {
            Spacer(modifier = Modifier.height(6.dp))
            Text("What it should be", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            p.shouldBe.forEach { BulletLine("•", it) }
        }
    }
}

@Composable
fun MemoryCard(facts: List<String>) {
    var expanded by remember { mutableStateOf(false) }
    AppCard(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp).animateContentSize()) {
            TextButton(onClick = { expanded = !expanded }) {
                Text(if (expanded) "Hide relationship memory" else "Show relationship memory (${facts.size})")
            }
            if (expanded) {
                Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                    facts.forEach { BulletLine("•", it) }
                }
            }
        }
    }
}

@Composable
fun SuppressedNote(count: Int) {
    if (count > 0) {
        Text(
            text = "$count suggestion${if (count == 1) "" else "s"} hidden because you marked similar ones " +
                "as not useful.",
            style = MaterialTheme.typography.bodySmall,
            color = MutedForeground
        )
    }
}
