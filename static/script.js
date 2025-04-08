
fetch('/get_rewards')
  .then(response => response.json())
  .then(data => {
    // Process the rewards data
    console.log(data);
    // Example: Display the rewards on the webpage
    data.forEach(reward => {
      const rewardElement = document.createElement('div');
      rewardElement.textContent = `${reward.pointsEarned} points - ${reward.rewardType}`;
      document.getElementById('rewards-container').appendChild(rewardElement);
    });
  })
  .catch(error => console.error('Error:', error));
