package com.eko.rcrm.dc.ui.officialedit

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.eko.rcrm.dc.domain.model.DcTerritory
import com.eko.rcrm.dc.ui.common.AppTopBar
import com.eko.rcrm.dc.ui.common.CtaButton
import com.eko.rcrm.dc.ui.common.ErrorBanner
import com.eko.rcrm.dc.ui.common.LoadingIndicator
import com.eko.rcrm.dc.ui.theme.Background
import com.eko.rcrm.dc.ui.theme.Border
import com.eko.rcrm.dc.ui.theme.MutedForeground
import com.eko.rcrm.dc.ui.theme.Primary
import com.eko.rcrm.dc.ui.theme.Surface

@Composable
fun OfficialEditScreen(
    onBack: () -> Unit,
    onSaved: () -> Unit,
    viewModel: OfficialEditViewModel = hiltViewModel()
) {
    val uiState by viewModel.uiState.collectAsState()

    LaunchedEffect(uiState.saved) {
        if (uiState.saved) onSaved()
    }

    Scaffold(
        containerColor = Background,
        topBar = {
            AppTopBar(
                title = if (uiState.isEdit) "Edit Official" else "Add Official",
                onBack = onBack
            )
        }
    ) { padding ->
        if (uiState.isLoadingInitial) {
            LoadingIndicator(modifier = Modifier.padding(padding))
            return@Scaffold
        }

        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(padding)
                .verticalScroll(rememberScrollState())
                .padding(20.dp)
        ) {
            LabeledField("Name *", uiState.name, viewModel::onNameChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Phone", uiState.phone, viewModel::onPhoneChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Email", uiState.email, viewModel::onEmailChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Designation", uiState.designation, viewModel::onDesignationChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Department", uiState.department, viewModel::onDepartmentChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Level", uiState.level, viewModel::onLevelChange)
            Spacer(modifier = Modifier.height(10.dp))
            LabeledField("Location", uiState.location, viewModel::onLocationChange)

            Spacer(modifier = Modifier.height(20.dp))
            Text(text = "Territory unit *", style = MaterialTheme.typography.titleMedium)
            Text(
                text = "Only your own assigned units can be picked - this is always a valid choice.",
                style = MaterialTheme.typography.bodySmall,
                color = MutedForeground
            )
            Spacer(modifier = Modifier.height(10.dp))

            if (uiState.territories.isEmpty()) {
                Text(
                    text = "No territory units assigned to you yet.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MutedForeground
                )
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    uiState.territories.forEach { unit ->
                        TerritoryOption(
                            unit = unit,
                            selected = unit.organizationUnitId == uiState.selectedOrganizationUnitId,
                            onClick = { viewModel.onOrganizationUnitSelected(unit.organizationUnitId) }
                        )
                    }
                }
            }

            uiState.error?.let {
                Spacer(modifier = Modifier.height(16.dp))
                ErrorBanner(message = it)
            }

            Spacer(modifier = Modifier.height(24.dp))

            if (uiState.isSubmitting) {
                CircularProgressIndicator(color = Primary)
            } else {
                CtaButton(
                    text = if (uiState.isEdit) "Save Changes" else "Create Official",
                    onClick = viewModel::submit,
                    enabled = uiState.name.isNotBlank(),
                    modifier = Modifier.fillMaxWidth()
                )
            }

            Spacer(modifier = Modifier.height(24.dp))
        }
    }
}

@Composable
private fun LabeledField(label: String, value: String, onChange: (String) -> Unit) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        singleLine = true,
        colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Primary),
        modifier = Modifier.fillMaxWidth()
    )
}

@Composable
private fun TerritoryOption(unit: DcTerritory, selected: Boolean, onClick: () -> Unit) {
    Card(
        shape = RoundedCornerShape(16.dp),
        colors = CardDefaults.cardColors(containerColor = if (selected) Primary.copy(alpha = 0.08f) else Surface),
        border = BorderStroke(if (selected) 1.5.dp else 1.dp, if (selected) Primary else Border),
        elevation = CardDefaults.cardElevation(defaultElevation = 0.dp),
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick)
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            horizontalArrangement = Arrangement.SpaceBetween
        ) {
            Column {
                Text(text = unit.organizationUnitName, style = MaterialTheme.typography.titleMedium)
                Text(text = unit.organizationUnitType, style = MaterialTheme.typography.bodySmall, color = MutedForeground)
            }
            if (selected) {
                Text(text = "Selected", style = MaterialTheme.typography.labelMedium, color = Primary)
            }
        }
    }
}
