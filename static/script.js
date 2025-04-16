
document.addEventListener("DOMContentLoaded", function () {
  const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');

  document.getElementById("submit-order").addEventListener("click", function () {
    fetch("/api/order-summary", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken  // ✅ required
      },
      body: JSON.stringify({
        orderData: {
          selectedItems: selectedItems  // your JS must define this
        }
      })
    })
      .then(res => res.json())
      .then(data => console.log("✅ Order placed:", data))
      .catch(err => console.error("❌ Order error:", err));
  });
});


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
