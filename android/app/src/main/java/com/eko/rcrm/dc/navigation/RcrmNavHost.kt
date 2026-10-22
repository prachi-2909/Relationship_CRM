package com.eko.rcrm.dc.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.eko.rcrm.dc.ui.history.CallHistoryScreen
import com.eko.rcrm.dc.ui.csp.CspListScreen
import com.eko.rcrm.dc.ui.home.HomeScreen
import com.eko.rcrm.dc.ui.login.LoginScreen
import com.eko.rcrm.dc.ui.manualdial.ManualDialScreen
import com.eko.rcrm.dc.ui.manuallog.ManualLogScreen
import com.eko.rcrm.dc.ui.manualtext.ManualTextEntryScreen
import com.eko.rcrm.dc.ui.officialdetail.OfficialDetailScreen
import com.eko.rcrm.dc.ui.officialedit.OfficialEditScreen
import com.eko.rcrm.dc.ui.officiallist.OfficialListScreen
import com.eko.rcrm.dc.ui.officialsearch.OfficialSearchScreen
import com.eko.rcrm.dc.ui.pending.PendingQueueScreen
import com.eko.rcrm.dc.ui.profile.ProfileScreen
import com.eko.rcrm.dc.ui.recording.RecordingCapabilityScreen
import com.eko.rcrm.dc.ui.review.CallReviewScreen
import com.eko.rcrm.dc.ui.session.SessionViewModel
import com.eko.rcrm.dc.ui.voicenote.VoiceNoteRecordingScreen

private val callSessionIdArg = navArgument(Routes.CALL_REVIEW_ARG) { type = NavType.IntType }
private val officialDetailIdArg = navArgument(Routes.OFFICIAL_DETAIL_ARG) { type = NavType.IntType }
private val officialEditIdArg = navArgument(Routes.OFFICIAL_EDIT_ARG) {
    type = NavType.IntType
    defaultValue = -1
}
private val officialListArgs = listOf(
    navArgument(Routes.OFFICIAL_LIST_UNIT_ID_ARG) { type = NavType.IntType; defaultValue = -1 },
    navArgument(Routes.OFFICIAL_LIST_UNIT_NAME_ARG) { type = NavType.StringType; nullable = true; defaultValue = null }
)

@Composable
fun RcrmNavHost(navController: NavHostController = rememberNavController()) {
    val sessionViewModel: SessionViewModel = hiltViewModel()

    LaunchedEffect(Unit) {
        sessionViewModel.sessionExpired.collect {
            navController.navigate(Routes.LOGIN) {
                popUpTo(0) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    NavHost(navController = navController, startDestination = Routes.LOGIN) {

        composable(Routes.LOGIN) {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.HOME) {
            HomeScreen(
                onSearchOfficials = { navController.navigate(Routes.OFFICIAL_SEARCH) },
                onAllOfficials = { navController.navigate(Routes.allOfficials()) },
                onManualDial = { navController.navigate(Routes.MANUAL_DIAL) },
                onLogCall = { navController.navigate(Routes.MANUAL_LOG) },
                onPendingQueue = { navController.navigate(Routes.PENDING_QUEUE) },
                onCallHistory = { navController.navigate(Routes.CALL_HISTORY) },
                onProfile = { navController.navigate(Routes.PROFILE) },
                onMyCsps = { navController.navigate(Routes.MY_CSPS) },
                onLoggedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.MY_CSPS) {
            CspListScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) }
            )
        }

        composable(Routes.PROFILE) {
            ProfileScreen(
                onBack = { navController.popBackStack() },
                onOpenUnit = { unitId, unitName -> navController.navigate(Routes.officialsForUnit(unitId, unitName)) },
                onOpenRecordingCapability = { navController.navigate(Routes.RECORDING_CAPABILITY) }
            )
        }

        composable(Routes.RECORDING_CAPABILITY) {
            RecordingCapabilityScreen(onBack = { navController.popBackStack() })
        }

        composable(Routes.MANUAL_DIAL) {
            ManualDialScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId ->
                    navController.navigate(Routes.callReview(callSessionId)) {
                        popUpTo(Routes.MANUAL_DIAL) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.MANUAL_LOG) {
            ManualLogScreen(
                onBack = { navController.popBackStack() },
                onLogged = { callSessionId ->
                    navController.navigate(Routes.callReview(callSessionId)) {
                        popUpTo(Routes.MANUAL_LOG) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.OFFICIAL_LIST, arguments = officialListArgs) {
            OfficialListScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) },
                onOpenDetail = { officialId -> navController.navigate(Routes.officialDetail(officialId)) },
                onEditOfficial = { officialId -> navController.navigate(Routes.officialEdit(officialId)) },
                onAddOfficial = { navController.navigate(Routes.officialCreate()) }
            )
        }

        composable(Routes.OFFICIAL_SEARCH) {
            OfficialSearchScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId ->
                    navController.navigate(Routes.callReview(callSessionId)) {
                        popUpTo(Routes.OFFICIAL_SEARCH) { inclusive = true }
                    }
                },
                onOpenDetail = { officialId -> navController.navigate(Routes.officialDetail(officialId)) },
                onAddOfficial = { navController.navigate(Routes.officialCreate()) }
            )
        }

        composable(Routes.OFFICIAL_DETAIL, arguments = listOf(officialDetailIdArg)) {
            OfficialDetailScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) },
                onEdit = { officialId -> navController.navigate(Routes.officialEdit(officialId)) }
            )
        }

        composable(Routes.OFFICIAL_EDIT, arguments = listOf(officialEditIdArg)) {
            OfficialEditScreen(
                onBack = { navController.popBackStack() },
                onSaved = { navController.popBackStack() }
            )
        }

        composable(Routes.PENDING_QUEUE) {
            PendingQueueScreen(
                onBack = { navController.popBackStack() },
                onOpenCall = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) }
            )
        }

        composable(Routes.CALL_HISTORY) {
            CallHistoryScreen(
                onBack = { navController.popBackStack() },
                onOpenCall = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) }
            )
        }

        composable(Routes.CALL_REVIEW, arguments = listOf(callSessionIdArg)) {
            CallReviewScreen(
                onBack = { navController.popBackStack() },
                onRecordVoiceNote = { callSessionId -> navController.navigate(Routes.voiceNoteRecording(callSessionId)) },
                onManualTextEntry = { callSessionId -> navController.navigate(Routes.manualTextEntry(callSessionId)) },
                onDone = {
                    val popped = navController.popBackStack(Routes.HOME, inclusive = false)
                    if (!popped) {
                        navController.navigate(Routes.HOME) { popUpTo(0) { inclusive = true } }
                    }
                }
            )
        }

        composable(Routes.VOICE_NOTE_RECORDING, arguments = listOf(callSessionIdArg)) {
            VoiceNoteRecordingScreen(
                onBack = { navController.popBackStack() },
                onSaved = { navController.popBackStack() }
            )
        }

        composable(Routes.MANUAL_TEXT_ENTRY, arguments = listOf(callSessionIdArg)) {
            ManualTextEntryScreen(
                onBack = { navController.popBackStack() },
                onSaved = { navController.popBackStack() }
            )
        }
    }
}
