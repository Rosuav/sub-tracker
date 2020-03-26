import choc, {set_content, on} from "https://rosuav.github.io/shed/chocfactory.js";
const {TR, TD} = choc;

const subsbody = document.querySelector("#subs tbody");
document.getElementById("filter").oninput = e => {
	const findme = e.currentTarget.value;
	console.log("Filter", findme);
	for (let tr = subsbody.firstChild; tr; tr = tr.nextSibling) {
		tr.classList.toggle("hidden", !tr.dataset.username.includes(findme));
		console.log(tr.dataset.username);
	}
};

set_content(subsbody, subscribers.map(s => TR(
	{"data-username": s.username, "data-userid": s.userid},
	[TD(s.username), TD(s.tenure === 1 ? "1 month" : s.tenure+" months"), TD(new Date(s.created).toDateString())]
)));
