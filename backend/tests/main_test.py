import unittest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app

class TestMainAPI(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    @patch('backend.services.draft_manager_service.DraftManagerService.initialize_draft')
    def test_start_draft(self, mock_initialize_draft):
        # Arrange
        mock_initialize_draft.return_value = {'session_id': 'test_session'}
        draft_settings = {
            'pick_slot': 1,
            'non_interactive': True,
            'teams': 12,
            'rounds': 15,
            'format': 'snake',
            'order': 'regular'
        }

        # Act
        response = self.client.post("/draft/simulation/start", json=draft_settings)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'session_id': 'test_session'})
        mock_initialize_draft.assert_called_once_with(
            pick_slot=1,
            draft_id=None,
            non_interactive=True,
            teams=12,
            rounds=15,
            format='snake',
            order='regular'
        )

    @patch('backend.services.draft_manager_service.DraftManagerService.get_current_draft_state')
    def test_get_draft_state(self, mock_get_current_draft_state):
        # Arrange
        mock_get_current_draft_state.return_value = {'state': 'test_state'}

        # Act
        response = self.client.get("/draft/simulation/test_session/state")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'state': 'test_state'})
        mock_get_current_draft_state.assert_called_once_with('test_session', None, None)

    @patch('backend.services.draft_manager_service.DraftManagerService.process_user_pick')
    def test_make_pick(self, mock_process_user_pick):
        # Arrange
        mock_process_user_pick.return_value = {'status': 'success'}
        player_pick = {'player_name': 'test_player'}

        # Act
        response = self.client.post("/draft/simulation/test_session/pick", json=player_pick)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success'})
        mock_process_user_pick.assert_called_once_with('test_session', 'test_player')

    @patch('backend.services.draft_manager_service.DraftManagerService.process_cpu_pick')
    def test_simulate_next_pick(self, mock_process_cpu_pick):
        # Arrange
        mock_process_cpu_pick.return_value = {'status': 'success'}

        # Act
        response = self.client.post("/draft/simulation/test_session/simulate-pick")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'success'})
        mock_process_cpu_pick.assert_called_once_with('test_session')

    @patch('backend.services.draft_manager_service.DraftManagerService.poll_live_draft_updates')
    def test_poll_live_draft(self, mock_poll_live_draft_updates):
        # Arrange
        mock_poll_live_draft_updates.return_value = {'status': 'updated'}

        # Act
        response = self.client.get("/draft/simulation/test_session/poll-live")

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'updated'})
        mock_poll_live_draft_updates.assert_called_once_with('test_session')

    @patch('backend.services.draft_manager_service.DraftManagerService.calculate_vona_for_display')
    def test_calculate_vona_endpoint(self, mock_calculate_vona_for_display):
        # Arrange
        mock_calculate_vona_for_display.return_value = {'player1': 10, 'player2': 20}
        request_data = {'player_names': ['player1', 'player2']}

        # Act
        response = self.client.post("/draft/simulation/test_session/calculate-vona", json=request_data)

        # Assert
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'player1': 10, 'player2': 20})
        mock_calculate_vona_for_display.assert_called_once_with('test_session', ['player1', 'player2'])

if __name__ == '__main__':
    unittest.main()