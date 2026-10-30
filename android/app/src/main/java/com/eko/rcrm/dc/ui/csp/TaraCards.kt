package com.eko.rcrm.dc.ui.csp

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.eko.rcrm.dc.domain.model.CspScore
import com.eko.rcrm.dc.domain.model.TaraPanel
import com.eko.rcrm.dc.ui.common.BulletLine
import com.eko.rcrm.dc.ui.common.SectionCard
import com.eko.rcrm.dc.ui.theme.MutedForeground
import java.util.Locale

/** 1,234 / 0 / 12.5 : a whole number without decimals, anything else with one. */
private fun num(v: Double?): String = when {
    v == null -> "—"
    v == Math.floor(v) -> String.format(Locale("en", "IN"), "%,d", v.toLong())
    else -> String.format(Locale("en", "IN"), "%,.1f", v)
}

private fun inr(v: Double?): String =
    if (v == null) "—" else "₹" + String.format(Locale("en", "IN"), "%,.0f", v)

private fun pct(v: Double?): String =
    if (v == null) "—" else (if (v > 0) "+" else "") + String.format(Locale.ENGLISH, "%.0f", v) + "%"

@Composable
private fun Score(label: String, value: Int?, missing: String) {
    Column(modifier = Modifier.fillMaxWidth().padding(top = 6.dp)) {
        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(text = label, style = MaterialTheme.typography.bodySmall)
            Text(
                text = value?.toString() ?: missing,
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
        }
        if (value != null) {
            LinearProgressIndicator(
                progress = { value.coerceIn(0, 100) / 100f },
                modifier = Modifier.fillMaxWidth().padding(top = 2.dp)
            )
        }
    }
}

/** How this CSP's relationship stands: overall, relationship and business (TARA), each with the reasons in words. */
@Composable
fun ScoreCard(score: CspScore) {
    SectionCard(title = "Relationship score", subtitle = score.band) {
        Row(verticalAlignment = Alignment.Bottom) {
            Text(text = score.overall.toString(), style = MaterialTheme.typography.displaySmall, fontWeight = FontWeight.Bold)
            Text(
                text = " / 100 overall",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground,
                modifier = Modifier.padding(start = 6.dp, bottom = 6.dp)
            )
        }
        Score("Relationship (contact, follow-through, picks up)", score.relationship, "—")
        Score(
            "Business (from TARA)", score.business,
            if (score.taraIncluded) "—" else "TARA figures not included"
        )
        if (score.reasons.isNotEmpty()) {
            Spacer(modifier = Modifier.height(10.dp))
            Text(text = "WHY", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            score.reasons.forEach { BulletLine("•", it) }
        }
    }
}

/** What TARA holds for this CSP right now. Every number is TARA's own, with its month and as-of; a target SBI has
 * not set shows as "not set", never as 0. */
@Composable
fun TaraCard(panel: TaraPanel) {
    var notes by remember { mutableStateOf(false) }

    if (!panel.available) {
        SectionCard(title = "TARA") {
            Text(
                text = "TARA's figures are not available right now. The score above uses the CRM's own records only.",
                style = MaterialTheme.typography.bodyMedium,
                color = MutedForeground
            )
        }
        return
    }

    SectionCard(
        title = "TARA says",
        subtitle = listOfNotNull(panel.month, panel.asOf?.let { "as of " + it.take(16).replace('T', ' ') }).joinToString(" · ")
    ) {
        panel.slab?.let { slab ->
            Text(text = "DFS SLAB", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            Text(
                text = "Reached: ${slab.reached ?: "none"}" +
                    (slab.target?.takeIf { it != "—" }?.let { " · aiming for $it" } ?: ""),
                style = MaterialTheme.typography.bodyMedium,
                fontWeight = FontWeight.SemiBold
            )
            slab.next?.let { n ->
                Text(
                    text = "Next: ${n.name ?: "slab"}" + (n.incentiveInr?.let { " (${inr(it)})" } ?: ""),
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
                n.schemes.forEach {
                    BulletLine(
                        "•",
                        "${it.scheme}: ${num(it.have)} of ${num(it.threshold)}" +
                            (if ((it.more ?: 0.0) > 0.0) " — ${num(it.more)} more" else " — done")
                    )
                }
                if (n.closestThree.isNotEmpty()) {
                    Text(
                        text = "Closest three: ${n.closestThree.joinToString(", ")}" +
                            (n.extraTotal?.let { " · ${num(it)} more in all" } ?: ""),
                        style = MaterialTheme.typography.bodySmall,
                        color = MutedForeground
                    )
                }
            }
            slab.rule?.let {
                Text(text = it, style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            }
            Spacer(modifier = Modifier.height(10.dp))
        }

        if (panel.products.isNotEmpty()) {
            Text(text = "THE FOUR SCHEMES THIS MONTH", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            panel.products.forEach { p ->
                val goal = p.taraGoal?.let { "TARA goal ${num(p.progress)} of ${num(it)}" +
                    (p.agentTarget?.let { s -> " (stretch ${num(s)})" } ?: "") } ?: "TARA goal not set"
                val sbi = p.sbiTarget?.let { "SBI target ${num(it)}" } ?: "SBI target not set"
                BulletLine(
                    "•",
                    "${p.name}: ${num(p.achieved)} done · $sbi · $goal" +
                        (p.pace?.let { " · ${it.replace('_', ' ')}" } ?: "")
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
        }

        if (panel.transactionsCount != null) {
            Text(text = "TRANSACTIONS THIS MONTH", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
            Text(
                text = "${num(panel.transactionsCount)} transactions · ${inr(panel.transactionsValueInr)}" +
                    (panel.lastDayWithData?.let { " · data up to $it" } ?: ""),
                style = MaterialTheme.typography.bodyMedium
            )
            Spacer(modifier = Modifier.height(10.dp))
        }

        if (panel.earnedInr != null) {
            Text(
                text = "EARNINGS" + (panel.earningsMonth?.let { " ($it)" } ?: ""),
                style = MaterialTheme.typography.labelSmall,
                color = MutedForeground
            )
            Text(
                text = "Earned ${inr(panel.earnedInr)} against a usual ${inr(panel.usualInr)}" +
                    (if (panel.growthPct != null) " (${pct(panel.growthPct)})" else "") +
                    (panel.earningsStatus?.let { " · $it" } ?: ""),
                style = MaterialTheme.typography.bodyMedium
            )
            if (panel.rankInDistrict != null) {
                Text(
                    text = "Rank in district: ${num(panel.rankInDistrict)} of ${num(panel.ofInDistrict)}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MutedForeground
                )
            }
            Spacer(modifier = Modifier.height(10.dp))
        }

        Text(text = "ACTIVITY AND KIT", style = MaterialTheme.typography.labelSmall, color = MutedForeground)
        BulletLine("•", "Last login: ${panel.lastLoginDate ?: "—"}")
        BulletLine("•", "Days without activity: ${num(panel.daysWithoutActivity)}")
        BulletLine("•", "Terminal: ${panel.terminalStatus ?: "—"}")
        BulletLine(
            "•",
            "mATM / passbook printer / GPS: " +
                listOf(panel.matmStatus, panel.passbookPrinterStatus, panel.gpsDongleStatus).joinToString(" / ") { it ?: "—" }
        )

        if (panel.caveats.isNotEmpty()) {
            TextButton(onClick = { notes = !notes }) {
                Text(if (notes) "Hide notes from TARA" else "Show notes from TARA (${panel.caveats.size})")
            }
            if (notes) panel.caveats.forEach { BulletLine("•", it) }
        }
    }
}
